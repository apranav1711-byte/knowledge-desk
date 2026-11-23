# Deploys the backend to AWS Lambda (container image + public HTTPS Function URL).
# Run from the project root in PowerShell:  .\deploy\deploy-aws.ps1
# Needs: AWS CLI logged in (aws sts get-caller-identity works), Docker running, backend\.env filled in.
$ErrorActionPreference = 'Stop'
$Region = 'ap-south-1'; $Name = 'accenture-api'; $Role = 'accenture-api-role'
$Frontend = 'https://accenture-knowledge-desk.vercel.app'

function Run($msg, [scriptblock]$cmd) { Write-Host "-> $msg"; & $cmd; if ($LASTEXITCODE -ne 0) { throw "Failed: $msg" } }

$acct = (aws sts get-caller-identity --query Account --output text); if ($LASTEXITCODE -ne 0) { throw 'AWS CLI is not logged in' }
$registry = "$acct.dkr.ecr.$Region.amazonaws.com"; $image = "$registry/${Name}:latest"

# 1. read secrets from backend\.env (never printed)
$envFile = Join-Path $PSScriptRoot '..\backend\.env'
if (-not (Test-Path $envFile)) { throw 'backend\.env not found' }
$vars = @{}
Get-Content $envFile | ForEach-Object { if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)$') { $vars[$Matches[1]] = $Matches[2].Trim() } }
foreach ($k in 'SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','DATABASE_URL') { if (-not $vars[$k] -or $vars[$k] -match 'YOUR-') { throw "Fill in $k in backend\.env first" } }
$lambdaEnv = @{
  SUPABASE_URL = $vars['SUPABASE_URL']; SUPABASE_SERVICE_ROLE_KEY = $vars['SUPABASE_SERVICE_ROLE_KEY']; DATABASE_URL = $vars['DATABASE_URL']
  CORS_ORIGINS = $Frontend; ENVIRONMENT = 'production'; INLINE_PROCESSING = 'true'; MODEL_CACHE_DIR = '/opt/models'
}
if ($vars['SUPABASE_JWT_SECRET']) { $lambdaEnv['SUPABASE_JWT_SECRET'] = $vars['SUPABASE_JWT_SECRET'] }
$envJson = Join-Path $env:TEMP 'lambda-env.json'
@{ Variables = $lambdaEnv } | ConvertTo-Json -Depth 4 | Set-Content -Encoding ascii $envJson

# 2. ECR repository + image
aws ecr describe-repositories --repository-names $Name --region $Region *> $null
if ($LASTEXITCODE -ne 0) { Run 'create ECR repository' { aws ecr create-repository --repository-name $Name --region $Region --output text --query repository.repositoryUri } }
Write-Host '-> docker login'; aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $registry
if ($LASTEXITCODE -ne 0) { throw 'docker login failed' }
Run 'build image (first time ~5-10 min)' { docker build --provenance=false -t $image (Join-Path $PSScriptRoot '..\backend') }
Run 'push image' { docker push $image }

# 3. IAM role for the function
aws iam get-role --role-name $Role *> $null
if ($LASTEXITCODE -ne 0) {
  $trust = Join-Path $env:TEMP 'trust.json'
  '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' | Set-Content -Encoding ascii $trust
  Run 'create IAM role' { aws iam create-role --role-name $Role --assume-role-policy-document "file://$trust" --output text --query Role.Arn }
  Run 'attach logging policy' { aws iam attach-role-policy --role-name $Role --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole }
  Start-Sleep -Seconds 12
}
$roleArn = "arn:aws:iam::${acct}:role/$Role"

# 4. Lambda function
aws lambda get-function --function-name $Name --region $Region *> $null
if ($LASTEXITCODE -ne 0) {
  Run 'create function' { aws lambda create-function --function-name $Name --package-type Image --code "ImageUri=$image" --role $roleArn --memory-size 3008 --timeout 300 --environment "file://$envJson" --region $Region --output text --query FunctionArn }
} else {
  Run 'update function code' { aws lambda update-function-code --function-name $Name --image-uri $image --region $Region --output text --query FunctionArn }
  aws lambda wait function-updated --function-name $Name --region $Region
  Run 'update function settings' { aws lambda update-function-configuration --function-name $Name --memory-size 3008 --timeout 300 --environment "file://$envJson" --region $Region --output text --query FunctionArn }
}
aws lambda wait function-active-v2 --function-name $Name --region $Region
aws lambda wait function-updated-v2 --function-name $Name --region $Region
Remove-Item $envJson -Force

# 5. public HTTPS URL (the app itself checks every login token)
aws lambda get-function-url-config --function-name $Name --region $Region *> $null
if ($LASTEXITCODE -ne 0) {
  Run 'create function URL' { aws lambda create-function-url-config --function-name $Name --auth-type NONE --region $Region --output text --query FunctionUrl }
  Run 'allow public URL access' { aws lambda add-permission --function-name $Name --statement-id url-public --action lambda:InvokeFunctionUrl --principal '*' --function-url-auth-type NONE --region $Region --output text --query Statement }
  aws lambda add-permission --function-name $Name --statement-id url-invoke --action lambda:InvokeFunction --principal '*' --invoked-via-function-url --region $Region *> $null
}
$url = (aws lambda get-function-url-config --function-name $Name --region $Region --query FunctionUrl --output text).TrimEnd('/')
Write-Host ''; Write-Host "API URL: $url"
Write-Host 'Health check (first call can take ~30s while the model loads):'
try { (Invoke-RestMethod "$url/api/v1/health" -TimeoutSec 120) | ConvertTo-Json -Depth 4 } catch { Write-Host $_.Exception.Message }

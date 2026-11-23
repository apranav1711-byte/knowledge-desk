"""Access-control lattice. Mirrors private.roles_for_classification() in the SQL migration."""
ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_HR, ROLE_ADMIN = "employee", "manager", "hr", "admin"
ALL_ROLES = [ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_HR, ROLE_ADMIN]

CLASSIFICATIONS = ["Public", "General_Internal", "Management", "HR_Confidential", "Restricted"]

# Non-linear lattice: Manager and HR have disjoint confidential domains; Admin sees everything in its tenant.
PERMISSION_MATRIX: dict[str, set[str]] = {
    "Public": set(ALL_ROLES),
    "General_Internal": set(ALL_ROLES),
    "Management": {ROLE_MANAGER, ROLE_ADMIN},
    "HR_Confidential": {ROLE_HR, ROLE_ADMIN},
    "Restricted": {ROLE_ADMIN},
}


def roles_for_classification(classification: str) -> list[str]:
    if classification not in PERMISSION_MATRIX:
        raise ValueError(f"Unknown classification '{classification}'. Allowed: {CLASSIFICATIONS}")
    return [r for r in ALL_ROLES if r in PERMISSION_MATRIX[classification]]


def can_read(role: str, classification: str) -> bool:
    return role in PERMISSION_MATRIX.get(classification, set())


def can_upload(role: str, classification: str) -> bool:
    """Delegated upload: you may only classify a document at a level you can read yourself. Employees never upload."""
    return role != ROLE_EMPLOYEE and can_read(role, classification)


def readable_classifications(role: str) -> list[str]:
    return [c for c in CLASSIFICATIONS if can_read(role, c)]

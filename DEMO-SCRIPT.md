# Knowledge Desk — demo video script (about 4 minutes)

**The story:** one company knowledge base, four people, four different views. Every answer is quoted from a
real document with its source, and nobody ever sees content above their clearance.

## Before you record (5 minutes)

1. Start the backend: double-click `start-knowledge-desk.cmd` and keep the window open.
2. Open https://knowledgedesk.vercel.app in Chrome. If Chrome asks about local network access, click **Allow**
   now, so the prompt doesn't appear on camera.
3. Sign in as yourself and ask any one question, so the search model is warmed up and the first on-camera answer is instant.
4. In **Documents**, delete **IT Security Handbook**, so you can upload it live in Scene 2
   (the file is `backend\demo\it-security-handbook.docx`).
5. Demo logins are in `backend\data\demo-accounts.txt`: Maya (Manager), Harish (HR) and Esha (Employee).
6. Chrome: zoom to 110–125 %, hide the bookmarks bar (Ctrl+Shift+B), and close other tabs.

## Scene 1 — Sign in (15 s)
- **Show:** the sign-in page, then sign in as yourself (Administrator).
- **Say:** "This is Knowledge Desk, a secure assistant for company policies. It answers only from your own
  documents, always shows the source, and respects who is allowed to see what."

## Scene 2 — Documents (40 s)
- **Click:** Documents. Point at the mix of formats (PDF, Word, Excel, PowerPoint, Markdown, text) and the
  classification badges: Public, General Internal, Management, HR Confidential and Restricted.
- **Do:** Add document → choose `it-security-handbook.docx` → General Internal → Upload & index. It turns **Ready** in a few seconds.
- **Say:** "Files are parsed, including their tables and headings, split into passages and indexed with their access level."

## Scene 3 — Ask questions as admin (60 s)
Open **Assistant** and ask these. Click the **[C1]** citation and **Open document** on one of them.

| Ask | Expected answer | Source (format) |
| --- | --- | --- |
| How often must passwords be changed? | at least 14 characters, changed every 90 days | IT Security Handbook (Word) |
| What is the hotel limit for a domestic trip? | INR 8,500 per night excluding taxes | Supplier travel policy (PDF) |
| When is the Diwali holiday? | 29 October 2027 (table row) | Holiday calendar (Excel) |
| How many days a week can I work remotely? | 2 days per week with manager approval | Remote work (Markdown) |

- **Say:** "No AI makes anything up here. Every sentence is quoted from a document and cited, and the Evidence
  panel shows exactly which passage it came from."

## Scene 4 — Same question, different people (70 s) ← the highlight
Sign out (top right), then sign in as each person and ask:

| Person | Ask | Expected |
| --- | --- | --- |
| **Esha** (Employee) | What is the Q4 revenue target? | "I cannot find sufficient information…" |
| **Maya** (Manager) | What is the Q4 revenue target? | **INR 42 crore** (PowerPoint, Management) |
| **Maya** (Manager) | What is the salary band for Grade G7? | "I cannot find…" (HR only) |
| **Harish** (HR) | What is the salary band for Grade G7? | **INR 1,200,000 to INR 1,800,000** |
| **Harish** (HR) | How many hires are planned for Engineering in 2027? | Engineering row: **45 planned hires** (Excel) |
| **Harish** (HR) | What is the Q4 revenue target? | "I cannot find…" (Management only) |

Optional: as Esha, open **Documents**. The Management, HR and Restricted files aren't even listed.
- **Say:** "The access check happens inside the database search itself, before anything is ranked. Restricted
  content is never retrieved, so it can't leak into an answer."

## Scene 5 — Admin controls (50 s)
Sign back in as yourself.
- Ask **What is the expansion budget for Project Cedar?** → **INR 25,000,000** (Restricted, admin only).
- **Users:** show the four people and their roles. Changing a role takes effect on that person's next request.
- **Audit:** click **Verify** (chain intact) and **Run security check** (**0 leaks** across every role).
- **Analytics:** questions asked, answer rate, questions by role.
- **Say:** "Every question and change is recorded in a tamper-evident audit log, and the built-in security test
  probes every document as every role to prove nothing leaks."

## Closing (10 s)
"Knowledge Desk: answers your team can trust, from documents they're allowed to see."

---
**If something goes wrong on camera:** "Cannot reach Knowledge Desk on this computer" means the backend window was closed,
so start it again. An answer of "I cannot find…" for an allowed question usually means the document is still indexing,
so wait a few seconds.

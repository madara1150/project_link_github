# Project GitHub Integration

โมดูล Odoo สำหรับเชื่อมต่อ GitHub Pull Requests กับ Project Tasks ใน Odoo แบบครบวงจร ทั้งการสร้าง Branch/PR จาก Odoo, รับข้อมูลผ่าน Webhook อัตโนมัติ, จัดการ Labels และ sync comments

- **Version:** 16.0.3.0.0
- **Author:** Aginix Technologies Co., ltd.
- **License:** LGPL-3
- **Category:** Project Management

---

## วิดีโอสอนใช้งาน

https://youtu.be/Zz5PNZbrCLQ

---

# ภาษาไทย

## ฟีเจอร์ทั้งหมด

### การเชื่อมต่อ GitHub Account
- เชื่อมต่อบัญชี GitHub ผ่าน OAuth 2.0 (ไม่ต้องพิมพ์ token เอง)
- แต่ละ User เชื่อมต่อบัญชี GitHub ของตัวเองได้อิสระ
- แสดงสถานะการเชื่อมต่อ (avatar + username) ใน User Profile
- ยกเลิกการเชื่อมต่อได้ตลอดเวลา

### การ Sync Repository
- ดึงรายการ Repository ทั้งหมดจาก GitHub มาเก็บใน Odoo
- เลือก Repository ที่ต้องการผูกกับ Project ผ่าน Wizard
- รองรับ Repository จำนวนมาก (paginated API, 100 repos ต่อหน้า)
- แต่ละ Repository บันทึกข้อมูล: ชื่อ, คำอธิบาย, default branch, สถานะ private/public

### การสร้าง Branch และ Pull Request จาก Odoo (ใหม่)
- กดปุ่ม **Create PR** ใน Task form ได้เลย ไม่ต้องออกไป GitHub
- เลือก Repository, Base Branch (`main` หรือ `16.0` เท่านั้น)
- ระบบสร้างชื่อ Branch อัตโนมัติในรูปแบบ `feat/{task-key}-{task-name}`
- สร้าง PR พร้อม description ที่มี Task reference อัตโนมัติ (ทำให้ webhook ผูก PR กับ Task ได้ทันที)
- URL, หมายเลข และสถานะ PR อัปเดตกลับมาที่ Task ทันทีหลังสร้างสำเร็จ

### การรับข้อมูล PR ผ่าน Webhook
- รับ event จาก GitHub อัตโนมัติเมื่อ PR เปิด, แก้ไข, ปิด หรือ merge
- ค้นหา Task จาก PR description โดยใช้ Task Key (เช่น `PROJ-42`)
- รองรับ PR เดียวที่ระบุหลาย Task พร้อมกัน
- ยืนยันความถูกต้องของ Webhook ด้วย HMAC-SHA256 Signature
- รองรับสองโหมดการค้นหา Task: Per-Project prefix และ Global fallback prefix

### การแสดงข้อมูล PR ใน Task
- แสดง PR URL (คลิกเปิด GitHub ได้)
- แสดงสถานะ PR แบบ color-coded badge: `open` (น้ำเงิน), `merged` (เขียว), `closed` (เทา)
- แสดง Labels ที่ติดอยู่บน PR
- แสดง PR Description พร้อม Markdown rendering (รองรับ code block, table, line break)

### การจัดการ Labels บน PR
- ปุ่ม **Approve PR** — ติด label `ok-to-merge` และถอด label `fix` อัตโนมัติ
- ปุ่ม **Request Changes** — ติด label `fix` และถอด label `ok-to-merge` อัตโนมัติ
- สร้าง label บน GitHub อัตโนมัติถ้ายังไม่มี
- ปุ่มแสดงเฉพาะเมื่อ User มีสิทธิ์ push/admin ใน Repository และ PR อยู่ในสถานะ `open`

### การ Sync Comments
- เปิดใช้ "Sync Comments to GitHub PR" ใน Task เพื่อให้ข้อความใน Odoo Chatter ส่งไปที่ GitHub PR Comment อัตโนมัติ
- ไม่กระทบการทำงานใน Odoo ถ้า sync ล้มเหลว (non-fatal)

---

## ความต้องการของระบบ

| รายการ | เวอร์ชัน |
|--------|---------|
| Odoo | 16.0 |
| Python | 3.8+ |

**Odoo Modules ที่ต้องติดตั้งก่อน:**
- `project` (มาพร้อม Odoo)
- `project_key` (ต้องติดตั้งแยก)

**Python Library (ไม่บังคับ แต่แนะนำ):**
```bash
pip install markdown
```
> หากไม่ติดตั้ง จะแสดง PR description เป็น plain text แทน

---

## วิธีติดตั้ง

### ขั้นตอนที่ 1: คัดลอกโมดูลเข้า Odoo

```bash
# Clone โดยตรงไปที่ addons directory
git clone https://github.com/madara1150/project_link_github.git /path/to/odoo/addons/project_github
```

### ขั้นตอนที่ 2: เพิ่ม Path ใน Odoo Config

เปิดไฟล์ `odoo.conf` แล้วเพิ่ม path:

```ini
[options]
addons_path = /path/to/odoo/addons,/path/to/odoo/custom-addons
```

### ขั้นตอนที่ 3: Restart Odoo และอัปเดต App List

```bash
sudo systemctl restart odoo
# หรือ
python odoo-bin -u all -d <database_name>
```

### ขั้นตอนที่ 4: ติดตั้งโมดูล

1. ไปที่ **Apps** ใน Odoo
2. คลิก **Update Apps List**
3. ค้นหา `Project GitHub Integration`
4. คลิก **Install**

---

## การตั้งค่า

### 1. ตั้งค่า GitHub OAuth App

1. ไปที่ GitHub → **Settings** → **Developer settings** → **OAuth Apps** → **New OAuth App**
2. กรอกข้อมูล:

| ช่อง | ค่า |
|------|-----|
| Application name | ชื่อแอปของคุณ |
| Homepage URL | `https://<your-odoo-domain>` |
| Authorization callback URL | `https://<your-odoo-domain>/github/oauth/callback` |

3. คัดลอก **Client ID** และ **Client Secret**

### 2. ตั้งค่าใน Odoo Settings

1. ไปที่ **Settings** → **General Settings** → section **GitHub Integration**
2. กรอกข้อมูล:

| ช่อง | คำอธิบาย |
|------|----------|
| **Client ID** | GitHub OAuth App Client ID |
| **Client Secret** | GitHub OAuth App Client Secret |
| **Webhook Secret** | รหัสลับสำหรับยืนยัน Webhook (กำหนดเองได้) |
| **Task Reference Prefix** | Prefix สำรองสำหรับ match task (เช่น `task`) |

3. คลิก **Save**

### 3. เชื่อมต่อบัญชี GitHub (ต่อ User)

1. คลิกที่ชื่อ User มุมขวาบน → **My Profile** (หรือ **Preferences**)
2. ไปที่แท็บ **GitHub**
3. คลิก **Connect with GitHub**
4. Authorize แอปใน GitHub
5. กลับมาที่ Odoo — แสดง avatar และ username เมื่อเชื่อมต่อสำเร็จ

### 4. ตั้งค่า GitHub Webhook

1. ไปที่ GitHub Repository → **Settings** → **Webhooks** → **Add webhook**
2. กรอกข้อมูล:

| ช่อง | ค่า |
|------|-----|
| Payload URL | `https://<your-odoo-domain>/github/webhook` |
| Content type | `application/json` |
| Secret | ค่าเดียวกับ Webhook Secret ใน Odoo Settings |
| Events | เลือก **Pull requests** |
| Active | เปิดใช้งาน |

3. คลิก **Add webhook**

### 5. ผูก Repository กับ Project

1. เปิด Project ที่ต้องการ → แท็บ **GitHub**
2. กรอก **GitHub Task Prefix** (เช่น `PROJ` — ใช้ match Task Key ใน PR body)
3. คลิก **Sync & Link Repos**
4. เลือก Repository ที่ต้องการผูก → คลิก **Confirm**

---

## วิธีใช้งาน

### สร้าง Branch และ PR จาก Task (วิธีใหม่)

1. เปิด Task ที่ต้องการ
2. คลิกปุ่ม **Create PR** ในแถบ header
3. กรอกข้อมูลในหน้าต่าง Wizard:
   - **Repository** — เลือก repo ที่ต้องการ (แสดงเฉพาะ repo ที่ผูกกับ Project นี้)
   - **Base Branch** — เลือก `main` หรือ `16.0`
   - **Branch Name** — ระบบสร้างให้อัตโนมัติ (แก้ไขได้) เช่น `feat/PROJ-42-fix-login-bug`
   - **PR Title** — ดึงจากชื่อ Task (แก้ไขได้)
   - **PR Description** — มี Task reference อัตโนมัติ (แก้ไขได้)
4. คลิก **Create PR**
5. Branch และ PR ถูกสร้างบน GitHub และ Task อัปเดต PR URL ทันที

### เชื่อม PR กับ Task (วิธีเดิมผ่าน Webhook)

เมื่อสร้าง PR บน GitHub ด้วยตนเอง ให้ระบุ Task Key ใน **description** ของ PR:

```
## Related Tasks
PROJ-42
PROJ-211
```

> รองรับทั้ง `PROJ-42`, `proj-42`, `Proj-42` (ไม่ case-sensitive)

### Approve หรือ Request Changes

1. เปิด Task ที่มี PR เชื่อมอยู่ (PR ต้องอยู่ในสถานะ `open`)
2. ใช้ปุ่มใน header:
   - **Approve PR** — ติด label `ok-to-merge`
   - **Request Changes** — ติด label `fix`

> ปุ่มแสดงเฉพาะเมื่อ User มีสิทธิ์ push/admin ใน Repository

### Sync Comments ไปยัง GitHub

1. เปิด Task → แท็บ **GitHub PR**
2. เปิดสวิตช์ **Sync Comments to GitHub PR**
3. ข้อความที่พิมพ์ใน Odoo Chatter จะถูกส่งไปที่ GitHub PR Comment อัตโนมัติ

---

## สถานะ PR

| สถานะ | สี | ความหมาย |
|------|----|----------|
| `open` | น้ำเงิน | PR ยังเปิดอยู่ รอ review หรือ merge |
| `merged` | เขียว | PR ถูก merge เข้า branch แล้ว |
| `closed` | เทา | PR ถูกปิดโดยไม่ merge |

---

## Data Flow

```
Odoo Task
    │
    │  (กดปุ่ม Create PR)
    ▼
POST /repos/{repo}/git/refs     ← สร้าง Branch
POST /repos/{repo}/pulls        ← สร้าง Pull Request
    │
    └─ อัปเดต github_pr_url, github_pr_number, github_pr_state ใน Task

GitHub Repository
    │
    │  (PR opened / edited / closed / merged)
    ▼
POST /github/webhook
    │
    ├─ ตรวจสอบ HMAC-SHA256 Signature
    ├─ อ่านข้อมูล PR (URL, number, state, labels, description)
    ├─ ค้นหา Task Key ใน PR description (เช่น PROJ-42)
    ├─ หา Task ที่ตรงกันใน Database
    └─ อัปเดต Task fields
```

---

## โครงสร้างไฟล์

```
project_github/
├── __manifest__.py
├── __init__.py
├── controllers/
│   ├── github_oauth.py          # OAuth flow + repo sync endpoint
│   └── github_webhook.py        # รับและประมวลผล Webhook จาก GitHub
├── models/
│   ├── github_repository.py     # Model เก็บข้อมูล Repository
│   ├── project_project.py       # เพิ่มฟีเจอร์ GitHub ใน Project
│   ├── project_task.py          # เพิ่ม fields + actions GitHub ใน Task
│   ├── res_config_settings.py   # ตั้งค่า OAuth, Webhook Secret, Prefix
│   └── res_users.py             # เก็บ GitHub token ต่อ User
├── views/
│   ├── github_repository_views.xml
│   ├── project_project_views.xml
│   ├── project_task_views.xml
│   ├── res_config_settings_views.xml
│   └── res_users_views.xml
├── wizard/
│   ├── create_pr_wizard.py            # Wizard สร้าง Branch + PR
│   ├── create_pr_wizard_views.xml
│   ├── github_repo_selector.py        # Wizard เลือก Repository
│   └── github_repo_selector_views.xml
├── static/src/js/
│   ├── github_login_widget.js   # Widget ปุ่ม Connect GitHub
│   └── github_notification.js   # แจ้งเตือนหลัง OAuth callback
└── security/
    └── ir.model.access.csv
```

---

## การแก้ไขปัญหา

**Webhook ไม่ทำงาน**
- ตรวจสอบว่า Odoo เข้าถึงได้จาก Internet (HTTPS)
- ตรวจสอบ Webhook Secret ว่าตรงกันทั้ง GitHub และ Odoo Settings
- ดู log: `tail -f /var/log/odoo/odoo.log | grep github`

**Task ไม่ถูก update หลัง PR event**
- ตรวจสอบว่า Task Key ใน PR description ตรงกับ format `{prefix}-{number}` (เช่น `PROJ-42`)
- ตรวจสอบว่า Repository ผูกกับ Project แล้ว และ Task Prefix ตั้งค่าถูกต้อง

**ปุ่ม Create PR / Approve PR ไม่แสดง**
- ตรวจสอบว่า User เชื่อมต่อ GitHub account แล้ว (ดูที่ Profile)
- สำหรับ Approve/Request Changes: ตรวจสอบว่า User มีสิทธิ์ push/admin ใน Repository

**PR Description ไม่แสดง Markdown**
- ติดตั้ง: `pip install markdown` แล้ว restart Odoo

---

## ฟีเจอร์ที่จะเพิ่มในอนาคต

- [ ] **Draft PR** — รองรับการสร้าง PR แบบ Draft จาก Odoo
- [ ] **Multi-repo PR** — เลือก repo หลายตัวพร้อมกันเมื่อสร้าง PR
- [ ] **PR Review Request** — ระบุ Reviewer ตอนสร้าง PR จาก Wizard
- [ ] **Auto-close Task** — ปิด Task อัตโนมัติเมื่อ PR ถูก merge
- [ ] **Task Stage Sync** — เปลี่ยน Stage ของ Task ตามสถานะ PR โดยอัตโนมัติ
- [ ] **GitHub Checks Integration** — แสดงผล CI/CD status ใน Task
- [ ] **Issue Linking** — เชื่อม GitHub Issues กับ Task นอกเหนือจาก PR
- [ ] **Bidirectional Comment Sync** — sync comment จาก GitHub PR กลับมาที่ Odoo Chatter ด้วย
- [ ] **PR Template** — กำหนด PR description template ต่อ Project

---
---

# English

## Features

### GitHub Account Connection
- Connect your GitHub account via OAuth 2.0 (no manual token entry)
- Each Odoo user connects their own GitHub account independently
- Displays connection status (avatar + username) in User Profile
- Disconnect at any time

### Repository Sync
- Pull all accessible repositories from GitHub into Odoo
- Select which repositories to link to each Project via a Wizard
- Handles large repo lists (paginated API, 100 repos per page)
- Stores repo metadata: name, description, default branch, private/public status

### Create Branch and Pull Request from Odoo (New)
- Click **Create PR** directly on the Task form — no need to leave Odoo
- Choose a Repository and Base Branch (`main` or `16.0` only)
- Branch name is auto-generated as `feat/{task-key}-{task-name}` (editable)
- PR body is pre-filled with a Task reference so the webhook links the PR to the Task automatically
- PR URL, number, and state are written back to the Task immediately after creation

### Webhook-driven PR Updates
- Automatically receives events from GitHub when a PR is opened, edited, closed, or merged
- Finds the matching Task by parsing the Task Key from the PR description (e.g. `PROJ-42`)
- One PR can reference multiple Tasks at once
- Validates webhook payloads with HMAC-SHA256 signature verification
- Two task-matching modes: per-project prefix and global fallback prefix

### PR Information in Task
- Displays PR URL (clickable, opens GitHub)
- Color-coded PR state badge: `open` (blue), `merged` (green), `closed` (grey)
- Displays PR labels
- Renders PR description with full Markdown support (code blocks, tables, line breaks)

### Label Management on PR
- **Approve PR** button — adds `ok-to-merge` label and removes `fix` label
- **Request Changes** button — adds `fix` label and removes `ok-to-merge` label
- Labels are created on the repository automatically if they don't exist
- Buttons are only visible when the user has push/admin access and the PR is `open`

### Comment Sync
- Enable "Sync Comments to GitHub PR" on a Task to mirror Odoo chatter messages to GitHub PR comments
- Non-fatal: if sync fails, the Odoo message is still saved normally

---

## System Requirements

| Item | Version |
|------|---------|
| Odoo | 16.0 |
| Python | 3.8+ |

**Required Odoo Modules:**
- `project` (bundled with Odoo)
- `project_key` (install separately)

**Optional Python Library (recommended):**
```bash
pip install markdown
```
> Without this, PR descriptions render as plain text instead of Markdown.

---

## Installation

### Step 1: Copy the Module into Odoo

```bash
git clone https://github.com/madara1150/project_link_github.git /path/to/odoo/addons/project_github
```

### Step 2: Add Path to Odoo Config

Open `odoo.conf` and add the path:

```ini
[options]
addons_path = /path/to/odoo/addons,/path/to/odoo/custom-addons
```

### Step 3: Restart Odoo and Update App List

```bash
sudo systemctl restart odoo
# or
python odoo-bin -u all -d <database_name>
```

### Step 4: Install the Module

1. Go to **Apps** in Odoo
2. Click **Update Apps List**
3. Search for `Project GitHub Integration`
4. Click **Install**

---

## Configuration

### 1. Create a GitHub OAuth App

1. GitHub → **Settings** → **Developer settings** → **OAuth Apps** → **New OAuth App**
2. Fill in:

| Field | Value |
|-------|-------|
| Application name | Your app name |
| Homepage URL | `https://<your-odoo-domain>` |
| Authorization callback URL | `https://<your-odoo-domain>/github/oauth/callback` |

3. Copy the **Client ID** and **Client Secret**

### 2. Configure Odoo Settings

1. Go to **Settings** → **General Settings** → **GitHub Integration**
2. Fill in:

| Field | Description |
|-------|-------------|
| **Client ID** | GitHub OAuth App Client ID |
| **Client Secret** | GitHub OAuth App Client Secret |
| **Webhook Secret** | Secret used to verify webhook payloads |
| **Task Reference Prefix** | Fallback prefix for task matching (e.g. `task`) |

3. Click **Save**

### 3. Connect a GitHub Account (per user)

1. Click your username (top-right) → **My Profile** (or **Preferences**)
2. Go to the **GitHub** tab
3. Click **Connect with GitHub**
4. Authorize the app in GitHub
5. Return to Odoo — avatar and username appear when connected

### 4. Set Up GitHub Webhook

1. GitHub Repository → **Settings** → **Webhooks** → **Add webhook**
2. Fill in:

| Field | Value |
|-------|-------|
| Payload URL | `https://<your-odoo-domain>/github/webhook` |
| Content type | `application/json` |
| Secret | Same value as Webhook Secret in Odoo Settings |
| Events | Select **Pull requests** |
| Active | Enabled |

3. Click **Add webhook**

### 5. Link a Repository to a Project

1. Open the Project → **GitHub** tab
2. Enter the **GitHub Task Prefix** (e.g. `PROJ` — used to match Task Keys in PR body)
3. Click **Sync & Link Repos**
4. Select the repositories to link → click **Confirm**

---

## Usage

### Create a Branch and PR from a Task (new)

1. Open the Task
2. Click **Create PR** in the form header
3. Fill in the Wizard:
   - **Repository** — select a repo (only repos linked to this project are shown)
   - **Base Branch** — choose `main` or `16.0`
   - **Branch Name** — auto-generated (editable), e.g. `feat/PROJ-42-fix-login-bug`
   - **PR Title** — pulled from Task name (editable)
   - **PR Description** — includes Task reference automatically (editable)
4. Click **Create PR**
5. The branch and PR are created on GitHub and the Task is updated with the PR URL immediately

### Link a PR to a Task (via Webhook)

When creating a PR manually on GitHub, include the Task Key in the PR **description**:

```
## Related Tasks
PROJ-42
PROJ-211
```

> Case-insensitive: `PROJ-42`, `proj-42`, and `Proj-42` all work.

### Approve or Request Changes

1. Open a Task that has a linked PR (PR must be `open`)
2. Use the header buttons:
   - **Approve PR** — adds `ok-to-merge` label
   - **Request Changes** — adds `fix` label

> Buttons are only visible when the user has push/admin access to the repository.

### Sync Comments to GitHub

1. Open a Task → **GitHub PR** tab
2. Enable **Sync Comments to GitHub PR**
3. Messages posted in the Odoo chatter are automatically sent to the GitHub PR as comments

---

## PR States

| State | Color | Meaning |
|-------|-------|---------|
| `open` | Blue | PR is open, awaiting review or merge |
| `merged` | Green | PR has been merged into the base branch |
| `closed` | Grey | PR was closed without merging |

---

## Data Flow

```
Odoo Task
    │
    │  (Click Create PR button)
    ▼
POST /repos/{repo}/git/refs     ← Create Branch
POST /repos/{repo}/pulls        ← Create Pull Request
    │
    └─ Write github_pr_url, github_pr_number, github_pr_state back to Task

GitHub Repository
    │
    │  (PR opened / edited / closed / merged)
    ▼
POST /github/webhook
    │
    ├─ Verify HMAC-SHA256 Signature
    ├─ Parse PR data (URL, number, state, labels, description)
    ├─ Find Task Key in PR description (e.g. PROJ-42)
    ├─ Look up matching Task in database
    └─ Update Task fields
```

---

## File Structure

```
project_github/
├── __manifest__.py
├── __init__.py
├── controllers/
│   ├── github_oauth.py          # OAuth flow + repo sync endpoint
│   └── github_webhook.py        # Webhook receiver and processor
├── models/
│   ├── github_repository.py     # Stored repository data
│   ├── project_project.py       # GitHub features on Project
│   ├── project_task.py          # GitHub fields + actions on Task
│   ├── res_config_settings.py   # OAuth, Webhook Secret, Prefix settings
│   └── res_users.py             # Per-user GitHub token storage
├── views/
│   ├── github_repository_views.xml
│   ├── project_project_views.xml
│   ├── project_task_views.xml
│   ├── res_config_settings_views.xml
│   └── res_users_views.xml
├── wizard/
│   ├── create_pr_wizard.py            # Branch + PR creation wizard
│   ├── create_pr_wizard_views.xml
│   ├── github_repo_selector.py        # Repository linking wizard
│   └── github_repo_selector_views.xml
├── static/src/js/
│   ├── github_login_widget.js   # Connect GitHub button widget
│   └── github_notification.js   # Post-OAuth callback notification
└── security/
    └── ir.model.access.csv
```

---

## Troubleshooting

**Webhook not receiving events**
- Ensure Odoo is accessible from the Internet (HTTPS required)
- Verify the Webhook Secret matches between GitHub and Odoo Settings
- Check logs: `tail -f /var/log/odoo/odoo.log | grep github`

**Task not updated after PR event**
- Verify the Task Key in the PR description matches the format `{prefix}-{number}` (e.g. `PROJ-42`)
- Verify the Repository is linked to the Project and the Task Prefix is set correctly

**Create PR / Approve PR buttons not showing**
- Verify the user has connected their GitHub account (check Profile)
- For Approve/Request Changes: verify the user has push/admin access to the Repository

**PR Description not rendering Markdown**
- Install: `pip install markdown` then restart Odoo

---

## Planned Features

- [ ] **Draft PR** — support creating draft PRs from Odoo
- [ ] **Multi-repo PR** — select multiple repos at once during PR creation
- [ ] **PR Review Request** — specify reviewers when creating a PR from the Wizard
- [ ] **Auto-close Task** — automatically close the Task when its linked PR is merged
- [ ] **Task Stage Sync** — move Task to a configured stage based on PR state changes
- [ ] **GitHub Checks Integration** — display CI/CD check results inside the Task
- [ ] **Issue Linking** — link GitHub Issues to Tasks in addition to PRs
- [ ] **Bidirectional Comment Sync** — sync GitHub PR comments back to Odoo Chatter
- [ ] **PR Template per Project** — configure a default PR description template per Project

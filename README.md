# Project GitHub Integration 33

โมดูล Odoo สำหรับเชื่อมต่อ GitHub Pull Requests กับ Project Tasks ใน Odoo โดยอัตโนมัติผ่าน Webhook

- **Version:** 16.0.1.0.0
- **Author:** Aginix Technologies Co., ltd.
- **License:** LGPL-3
- **Category:** Project Management

---

## ฟีเจอร์หลัก

- รับข้อมูล Pull Request จาก GitHub ผ่าน Webhook โดยอัตโนมัติ
- อัปเดต Task ใน Odoo เมื่อ PR มีการเปลี่ยนแปลง (เปิด, แก้ไข, ปิด, merge)
- ตรวจจับ Task ID จาก PR description อัตโนมัติ (เช่น `task-42`, `TASK-211`)
- แสดงสถานะ PR แบบ color-coded (open = น้ำเงิน, merged = เขียว, closed = เทา)
- แสดง PR description พร้อม Markdown rendering (รองรับ code block, table)
- รองรับ PR เดียวที่ระบุหลาย Task พร้อมกัน
- ป้องกันการปลอมแปลง Webhook ด้วย HMAC-SHA256 Signature

---

## วิดีโอสอนใช้งาน
https://youtu.be/Zz5PNZbrCLQ

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
# วิธีที่ 1: Clone โดยตรงไปที่ addons directory
git clone https://github.com/<your-username>/project_link_github.git /path/to/odoo/addons/project_link_github

# วิธีที่ 2: Copy โฟลเดอร์โมดูลไปไว้ใน custom addons path
cp -r project_link_github /path/to/odoo/custom-addons/
```

### ขั้นตอนที่ 2: เพิ่ม Path ใน Odoo Config

เปิดไฟล์ `odoo.conf` แล้วเพิ่ม path ของโมดูล:

```ini
[options]
addons_path = /path/to/odoo/addons,/path/to/odoo/custom-addons
```

### ขั้นตอนที่ 3: Restart Odoo และอัปเดต App List

```bash
# Restart Odoo service
sudo systemctl restart odoo

# หรือรัน Odoo ด้วย flag update
python odoo-bin -u all -d <database_name>
```

### ขั้นตอนที่ 4: ติดตั้งโมดูล

1. ไปที่ **Apps** ใน Odoo
2. คลิก **Update Apps List** (ถ้ายังไม่เห็นโมดูล)
3. ค้นหา `Project GitHub Integration`
4. คลิก **Install**

---

## การตั้งค่า

### ตั้งค่าใน Odoo

1. ไปที่ **Settings** → **General Settings**
2. เลื่อนหา section **"GitHub Integration"**
3. กรอกข้อมูล:

| ช่อง | คำอธิบาย | ตัวอย่าง |
|------|----------|---------|
| **Webhook Secret** | รหัสลับสำหรับยืนยันความถูกต้องของ Webhook (ต้องตรงกับที่ตั้งใน GitHub) | `my-secret-key-123` |
| **Task Reference Prefix** | คำนำหน้า Task ID ที่ใช้ใน PR description | `task` |

4. คลิก **Save**

> **หมายเหตุ:** Webhook URL ของคุณคือ `https://<your-odoo-domain>/github/webhook`

### ตั้งค่า GitHub Webhook

1. ไปที่ GitHub Repository ที่ต้องการเชื่อมต่อ
2. คลิก **Settings** → **Webhooks** → **Add webhook**
3. กรอกข้อมูล:

| ช่อง | ค่าที่ต้องกรอก |
|------|--------------|
| **Payload URL** | `https://<your-odoo-domain>/github/webhook` |
| **Content type** | `application/json` |
| **Secret** | ค่าเดียวกับที่กรอกใน Odoo Settings |
| **Which events?** | เลือก **"Let me select individual events"** แล้วติ๊ก **Pull requests** |
| **Active** | เปิดใช้งาน |

4. คลิก **Add webhook**

---

## วิธีใช้งาน

### เชื่อม PR กับ Task

เมื่อสร้าง Pull Request บน GitHub ให้ระบุ Task ID ใน **description** ของ PR:

```
## สิ่งที่เปลี่ยนแปลง
- เพิ่มฟีเจอร์ login ด้วย SSO

## Related Tasks
task-42
task-211
```

> รองรับทั้ง `task-42`, `TASK-42`, `Task-42` (ไม่ sensitive ตัวพิมพ์เล็กใหญ่)

### ดูข้อมูล PR ใน Odoo Task

1. ไปที่ **Project** → เลือก Task ที่ถูก link
2. คลิก Tab **"GitHub PR"** เพื่อดู:
   - PR URL (คลิกเพื่อเปิด GitHub ได้)
   - PR Number
   - สถานะ PR (open / merged / closed)
3. คลิก Tab **"GitHub PR Description"** เพื่อดูรายละเอียด PR แบบ Markdown

### สถานะ PR ที่รองรับ

| สถานะ | สี | ความหมาย |
|------|----|----------|
| `open` | น้ำเงิน | PR ยังเปิดอยู่ |
| `merged` | เขียว | PR ถูก merge เข้า branch แล้ว |
| `closed` | เทา | PR ถูกปิดโดยไม่ merge |

---

## Data Flow

```
GitHub Repository
      │
      │  (PR opened / edited / closed / merged)
      ▼
POST /github/webhook
      │
      ├─ ตรวจสอบ HMAC-SHA256 Signature
      ├─ อ่านข้อมูล PR (URL, number, state, description)
      ├─ ค้นหา task-XXX ใน PR description
      ├─ หา Task ที่ตรงกันใน Database
      └─ อัปเดต Task fields
            │
            ▼
     project.task (Odoo)
     ├─ github_pr_url
     ├─ github_pr_number
     ├─ github_pr_state
     └─ github_pr_description
```

---

## โครงสร้างไฟล์

```
project_link_github/
├── __manifest__.py                    # ข้อมูลโมดูล (ชื่อ, version, dependencies)
├── __init__.py
├── controllers/
│   ├── __init__.py
│   └── github_webhook.py              # รับและประมวลผล Webhook จาก GitHub
├── models/
│   ├── __init__.py
│   ├── project_task.py                # เพิ่ม fields GitHub ใน Task
│   └── res_config_settings.py         # การตั้งค่า (secret, prefix)
├── views/
│   ├── project_task_views.xml         # UI แสดงข้อมูล PR ใน Task form
│   └── res_config_settings_views.xml  # UI ตั้งค่าใน Settings
└── security/
    └── ir.model.access.csv            # สิทธิ์การเข้าถึง
```

---

## การแก้ไขปัญหา

**Webhook ไม่ทำงาน / ไม่ได้รับข้อมูล**
- ตรวจสอบว่า Odoo เข้าถึงได้จาก Internet (GitHub ต้องส่ง request มาได้)
- เปิด HTTPS บน Odoo server
- ตรวจสอบ Webhook Secret ว่าตรงกันทั้ง GitHub และ Odoo Settings

**Task ไม่ถูก update**
- ตรวจสอบว่า Task ID ที่ระบุใน PR description ตรงกับ Task ที่มีอยู่ใน Odoo
- ตรวจสอบ prefix ใน Settings ว่าตรงกับที่ใช้ใน PR (เช่น `task` vs `TASK`)

**PR Description ไม่แสดง Markdown**
- ติดตั้ง Python library: `pip install markdown`
- Restart Odoo หลังติดตั้ง

**ดู Log เพื่อ Debug**
```bash
tail -f /var/log/odoo/odoo.log | grep github
```

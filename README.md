# Smart Attendance Automation System

A reliable, safe browser-automation desktop application for the Karnataka
Department of Social Welfare attendance portal.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Running the Application](#running-the-application)
4. [Configuring the Portal URL](#configuring-the-portal-url)
5. [Manual Sign-In](#manual-sign-in)
6. [Selecting a Student and Reason](#selecting-a-student-and-reason)
7. [Starting and Stopping Automation](#starting-and-stopping-automation)
8. [Troubleshooting Slow Servers](#troubleshooting-slow-servers)
9. [Running Tests](#running-tests)
10. [Building the Windows EXE](#building-the-windows-exe)
11. [Project Structure](#project-structure)
12. [Important Notices](#important-notices)

---

## Prerequisites

| Software | Minimum Version | Notes |
|----------|-----------------|-------|
| Python   | 3.10            | [python.org/downloads](https://www.python.org/downloads/) |
| pip      | 22+             | Included with Python |
| Git      | Any             | Optional – for cloning |

A working internet connection is required to download Playwright browsers
and to reach the attendance portal.

---

## Installation

### 1. Create a virtual environment

```powershell
cd "c:\Users\iu\ATT AUTO"
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install Python dependencies

```powershell
pip install -r requirements.txt
```

### 3. Install Playwright browsers

```powershell
playwright install chromium
```

Chromium is the default browser.  If you prefer Firefox or WebKit:

```powershell
playwright install firefox
playwright install webkit
```

---

## Running the Application

```powershell
python main.py
```

The desktop dashboard will open immediately.

---

## Configuring the Portal URL

1. Click **⚙ Settings** in the top-right corner of the dashboard.
2. Paste the full URL of the Karnataka Department of Social Welfare
   attendance portal into the **Portal URL** field.
   - Example: `https://portal.kswdc.gov.in/manual-attendance`
3. Select the browser you want to use (Chromium / Firefox / WebKit).
4. Click **💾 Save**.

> ⚠ **Never share your portal URL if it contains session tokens or one-time
> parameters.**

---

## Manual Sign-In

The application **never** collects, stores, or transmits your username or
password.

1. Click **🌐 Open Portal** on the left panel.
2. A browser window opens at the portal URL you configured.
3. Log in manually using your authorised credentials.
4. Wait until the **Manual Attendance** form is visible.
5. The application automatically reads the available dropdown options
   (dates, students, reasons) from the form and populates the dashboard.

---

## Selecting a Student and Reason

### Single-student mode (default)

- Enter the student's name or ID in the **Student** field.

### Multi-student mode

- Enter one student name per line in the **Student List** text box.
- Each student is processed in order with a confirmation dialog
  before each submission (when Require Confirmation is enabled).

### Loading the student list from the portal

- Click **🔄 Load from Portal** to read the dropdown options directly
  from the live page.

### Selecting the reason

- The **Reason** dropdown is populated from the portal's live dropdown.
- If the dropdown could not be loaded, you can type the exact reason
  text manually.
- Available reasons (based on the portal screenshots):
  - Network Not Available
  - No Power
  - System Was Down
  - Thumb Not Detected
  - Software Not Working Due to Configuration Problem

> ⚠ **Never select an inaccurate reason.  Only choose the reason that
> accurately describes the actual situation.**

---

## Starting and Stopping Automation

| Button            | Action                                      |
|-------------------|---------------------------------------------|
| ▶ Start Automation | Begin the configured attendance jobs        |
| ⏸ Pause           | Pause after the current step finishes       |
| ▶ Resume          | Continue from where it was paused           |
| ⏹ Stop            | Halt automation safely at the next safe point |

A **confirmation dialog** appears before each submission (configurable in
Settings → Require Confirmation).

---

## Understanding the Results

| Colour | Meaning            |
|--------|--------------------|
| 🟢 Green | Attendance marked successfully |
| 🟡 Amber | Already marked or warning |
| 🔴 Red   | Error or failure   |

The **Activity Log** panel shows a timestamped record of every action.
The log is saved to `logs/activity.log`.

---

## Troubleshooting Slow Servers

| Symptom | Solution |
|---------|----------|
| "Page-load timeout" | Increase **Page-Load Timeout** in Settings |
| "Element not found" | Increase **Element Timeout** in Settings |
| Repeated failures   | Reduce **Max Retries** and check the portal manually |
| Session expired     | Close the browser, click Open Portal, log in again |
| Browser disconnected | Restart the application |

The application uses **exponential back-off**: after a timeout it waits
2 s, then 4 s, then 8 s before each retry.  It never submits blindly
after an unknown result.

---

## Running Tests

```powershell
# Activate the venv first
pytest tests/ -v
```

Tests do **not** submit real attendance records.  They use in-memory
mocks and temporary configuration files.

---

## Building the Windows EXE

> Requires PyInstaller (already in requirements.txt).

```powershell
pyinstaller smart_attendance.spec
```

The executable will be created at:

```
dist\SmartAttendance.exe
```

Copy the entire `dist\` directory to the target machine.  No Python
installation is required on the target.

### Post-build checklist

- [ ] Copy `config\settings.json` next to the EXE (or let the app
      create it on first run).
- [ ] Run `playwright install chromium` on the target machine if
      the bundled browser fails to start.  (Playwright browsers are
      not bundled by PyInstaller by default.)
- [ ] Alternatively, install `playwright` and run
      `playwright install chromium` once on the target.

---

## Project Structure

```
smart_attendance/
├── main.py                      ← Entry point
├── requirements.txt
├── smart_attendance.spec        ← PyInstaller build script
├── README.md
├── config/
│   └── settings.json            ← User preferences (auto-created)
├── logs/
│   └── activity.log             ← Activity log (auto-created)
├── app/
│   ├── __init__.py
│   ├── configuration.py         ← Settings load/save/validate
│   ├── logging_manager.py       ← Timestamped logging
│   ├── browser_manager.py       ← Playwright lifecycle
│   ├── page_detection.py        ← Form detection & dropdown reading
│   ├── attendance_workflow.py   ← Automation orchestration
│   └── dashboard.py             ← CustomTkinter UI
└── tests/
    ├── __init__.py
    ├── test_configuration.py
    ├── test_result_detection.py
    └── test_retry_logic.py
```

---

## Important Notices

1. **Authorised use only** — This tool automates the official Karnataka
   Department of Social Welfare portal on behalf of authorised staff.
   Use it only for students and dates you are authorised to manage.

2. **No password storage** — The application never stores, logs, or
   transmits portal passwords or session tokens.

3. **No CAPTCHA bypass** — The application does not attempt to solve or
   circumvent CAPTCHA or any other authentication control.

4. **Accurate reasons** — Always select the reason that truthfully
   describes why biometric attendance could not be recorded.

5. **Portal selector verification** — After opening the portal for the
   first time, inspect the page (F12 → Elements in the browser) and
   compare the actual HTML IDs with the selectors in
   `app/page_detection.py`.  Update those selectors to match the real
   portal DOM for reliable automation.

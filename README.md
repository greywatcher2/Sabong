# Cockpit (Desktop App)

This is a Windows desktop app (a normal window program) built with **Python + Tkinter**. It stores everything in a local **SQLite** database file on your computer (no internet required).

It is designed to help you run an event with:

- **Fight Registry**: create matches, add entries, start/stop, set results
- **Cashiering / Betting**: encode bets, print slips, and pay out using QR payload text
- **Roles & Permissions**: control who can do what
- **Audit Log**: an append-only “history book” of important actions
- **Public Display**: fullscreen “viewer” screen for showing the current match + odds

## A kid-friendly explanation (very simple)

Think of this app like a **big notebook + cash register + ticket printer**.

- The notebook part remembers matches and entries.
- The cash register part remembers money going in (bets) and money going out (payouts/refunds).
- The ticket printer part prints a “bet slip” that has a **QR code** and also shows the **QR text** (the “secret code”).
- The audit log is like a **security camera logbook**: it remembers who did what, and you can’t erase it.

Everything is saved to a file on your computer, like saving a game.

## What you need

- Windows
- Python 3 installed
- Python must include **Tkinter** (the built-in library that draws windows)

No extra packages are required to run the app.

## How to run (step-by-step)

### 1) Open the folder

Open PowerShell (or Windows Terminal) and go to the project folder:

```powershell
cd E:\Project\Cockpit
```

### 2) Start the app

Run:

```powershell
python main.py
```

What happens next:

- The app creates/opens the database automatically.
- A window opens.

## First run: create the first Admin

The very first time you run the app, there are **no users** yet. So the app shows an **Initial Setup** screen.

Do this:

1. Pick a username (default is `admin`)
2. Type a password
3. Type the same password again
4. Click **Create Admin**

After you create the Admin, you’ll be taken to the login screen.

## Log in

1. Type your username
2. Type your password
3. Click **Login**

Important rule:

- One user account can only be logged in on **one computer/device at a time**. If you try to log in again elsewhere, it will refuse (to prevent double-using the same account).

## Your main screens (what each one does)

After login you’ll see buttons on the left side. Which buttons you see depends on your role/permissions.

- **Dashboard**: quick overview (if your role has access)
- **Fight Registry**: create matches, add entries, start/stop, set results
- **Cashiering / Betting**: encode bets, print slips, and pay out
- **Canteen**: a basic POS screen (if enabled for your role)
- **Roles & Permissions**: create roles and choose permissions (Admin)
- **Reports**: view reports (if enabled)
- **Audit Log**: view the “cannot-delete” history of actions
- **User Management**: create users, freeze/unfreeze, assign roles

## Typical workflow (the “do this in order” guide)

### Part A — Create a match and entries (Fight Registry)

1. Go to **Fight Registry**
2. Click **New Match**
3. Type a **Match number** (must be unique)
4. Choose a **Structure code** (the app will show you the valid codes)
5. Choose **Rounds** (usually `1`)
6. Confirm

Now add entries:

1. Select your match in the list
2. Click **Add Entry**
3. Choose the side: `WALA` or `MERON`
4. Fill in entry details (name, owner, number of cocks, weight, color)
5. Confirm

Important note:

- Once betting starts on a match, it becomes **LOCKED** automatically, and you can’t edit entries anymore.

### Part B — Encode a bet and print a slip (Cashiering / Betting)

1. Go to **Cashiering / Betting**
2. Select a match
3. Choose a side: `WALA`, `MERON`, or `DRAW`
4. Enter the amount (minimum is ₱10)
5. Click **Encode + Print Slip**

What printing does:

- The app creates a small HTML slip file and asks Windows to print it.
- The slip shows the bet details and a QR code.
- It also shows the raw **QR Payload text** (so you can copy/paste it if you don’t have a scanner).

### Part C — Payout using the QR payload text

When someone wants to claim winnings (or a refund), you “scan” the QR text:

1. Go to **Cashiering / Betting**
2. In **Payout (Scan QR text)** paste the QR payload text (or scan it with a scanner that types into the box)
3. Click **Payout**

If the slip is valid and eligible, the app records the payout and updates cash movements.

### Part D — Set the match result (Fight Registry)

1. Go back to **Fight Registry**
2. Select the match
3. Click **Set Result**
4. Enter one of:
   - `WALA`
   - `MERON`
   - `DRAW`
   - `CANCELLED`
   - `NO_CONTEST`

Then payouts/refunds follow the rules coded into the system.

## Public display mode (fullscreen viewer)

This mode is for a big screen / projector. It shows the latest match and the current totals/odds.

Start it like this:

```powershell
python main.py --viewer
```

How to exit:

- Press **Escape**

## User Management (Admin)

### Create a user

1. Go to **User Management**
2. Click **Create User**
3. Pick a username, password, and role

### Freeze / unfreeze a user

Freezing is like “temporarily lock this account”.

1. Select a user
2. Click **Freeze/Unfreeze**
3. Type a reason

### Assign roles

1. Select a user
2. Click **Set Roles**
3. Tick the roles you want
4. Save

## Roles and permissions (simple explanation)

- A **role** is like a job title (Cashier, Registrar, Admin).
- A **permission** is a single “power” (like “can payout”).
- A role is just a bundle of permissions.

This app seeds default roles like:

- Admin
- Cashier
- Fight Registrar
- Canteen
- Supervisor / Auditor

## Where your data is saved (important)

The database file is created in your Windows user home folder:

- Folder: `%USERPROFILE%\.cockpit\`
- File: `cockpit.sqlite3`

If you want to back up your data:

1. Close the app
2. Copy `cockpit.sqlite3` to a safe place (USB drive, another folder, etc.)

## Troubleshooting

### “No module named tkinter” (or the app opens and crashes instantly)

Your Python may not include Tkinter.

Fix:

- Install the normal Windows Python from python.org, and make sure Tkinter is included.

### Printing doesn’t print

The app asks Windows to print an HTML file. If printing fails:

- Make sure a default printer is set
- If the print dialog appears, choose a printer
- If nothing prints, Windows may open the file instead; the slip is still created

### “User already logged in on another device”

That user account is still logged in somewhere else. Log out from the other computer/device (or close the app there) and try again.

## Developer checks (optional)

From the project folder you can run:

```powershell
python -m compileall -q cockpit main.py
python -m unittest discover -s tests -p "test_*.py"
```

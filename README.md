# keepass-tui

**A full-featured TUI password manager for KeePassXC**

A simple, fast, and convenient tool for working with `.kdbx` databases. Supports all major operations: viewing, creating, editing, and deleting entries and groups.

Built with the `curses` library — no heavy dependencies or bloated interface.

## Features

- File-manager-like navigation through groups
- View, create, edit, and delete entries and groups
- Flat list of all entries with incremental search by title and username (`/`)
- Copy password to clipboard with a single key
- Change password on a remote server via SSH (single and bulk)
- Check passwords for breaches using Have I Been Pwned (with K-anonymity)
- Support for master password and key file

## Password Breach Checking

The application checks compromised passwords via the official **Have I Been Pwned** API using **K-anonymity**. This allows safe checking without sending the password in plain text to the server.

## Project Structure

```
keepass_tui
├── src
│   └── keepass_tui                        # main package
│        ├── main.py                       # entry point
│        ├── ui
│        │   ├── colors.py                 # curses color palette
│        │   ├── widgets.py                # primitives: frames, dialogs, input-box
│        │   └── clipboard.py              # clipboard support (Linux / macOS / Windows)
│        ├── keepass
│        │   └── db.py                     # CRUD operations with KeePass database
│        ├── security
│        │   ├── generator.py              # password generation
│        │   └── hibp.py                   # breach checking
│        ├── ssh
│        │   └── passwords.py              # SSH password changing
│        └── screens
│            ├── auth.py                   # authorization screen
│            ├── file_picker.py            # .kdbx file selection
│            ├── main_menu.py              # main menu
│            ├── entry_list.py             # entry list + search
│            ├── entry_detail.py           # detailed entry view
│            ├── group_browser.py          # group navigation
│            ├── pwned_screen.py           # password breach check screen
│            └── ssh_screens.py            # SSH password change screens
│
└── tests                                  # tests
     ├── data                              # test data folder
     ├── integration                       # integration tests
     │    ├── test_record_and_dir.py       # CRUD tests for entries and groups
     │    └── test_ssh_change_password.py  # SSH password change tests
     └── unit                              # unit tests
          ├── test_password_entropy.py     # password entropy tests
          └── test_tmp_file_helpers.py     # helper tests
```

## Testing

The project includes both **unit** and **integration** tests.

### Run all tests:

```bash
PYTHONPATH=src uv run python -m unittest discover -s tests -v
```

## Requirements

- Python **3.10+**
- [`uv`](https://docs.astral.sh/uv/) — environment and dependency manager
- For SSH password changing: `paramiko` (optional)
- For clipboard on Linux: `xclip` or `xsel`

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/Alextezinn/keepass_tui.git
cd keepass_tui
```

### 2. Create virtual environment and install dependencies

```bash
uv venv
uv sync
```

Activate the environment:

```bash
# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

### 3. Run

```bash
python src/main.py
```

## Controls

| Screen        | Key             | Action              |
|---------------|-----------------|---------------------|
| Entry List    | `↑` / `↓`       | Navigation          |
|               | `Enter`         | Open entry          |
|               | `/`             | Search              |
|               | `r`             | Change password via SSH |
|               | `R`             | Bulk SSH password change |
|               | `b`             | Breach check        |
|               | `B`             | Bulk Breach Check   |
|               | `q` / `Esc`     | Back                |
| Entry View    | `p`             | Show / hide password |
|               | `c`             | Copy password to clipboard |
|               | `r`             | Change password via SSH |
| Group Browser | `a`             | Create entry        |
|               | `f`             | Create group        |
|               | `e`             | Edit                |
|               | `d`             | Delete              |
| Authorization | `Tab`           | Switch field        |

## SSH: Password Change

In the **URL** field of an entry, specify the server IP or hostname:

```
192.168.1.10
ssh://myserver.example.com
```

When you press `r`, the app will connect via SSH using the credentials from the entry, generate a new password, change it using `chpasswd` via `sudo`, and automatically save it back to the KeePass database.

> ⚠️ This feature requires that the user has permission to run `sudo chpasswd`
> without interactive confirmation (or that the current password is accepted by `sudo -S`).

## Dependencies

| Package       | Purpose                                      | Required     |
|---------------|----------------------------------------------|:------------:|
| `pykeepass`   | Create, read and write `.kdbx` files         | ✅           |
| `paramiko`    | SSH connection for password changing         | ➖ optional  |
| `pre-commit`  | Code quality checks before commit            | ➖ optional  |

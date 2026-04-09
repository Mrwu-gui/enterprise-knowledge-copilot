#!/usr/bin/env bash
set -euo pipefail

OLD_RELEASE="/opt/lok/releases/20260403-103504"
NEW_RELEASE="/opt/lok/releases/20260408-185629"
CURRENT_LINK="/opt/lok/current"
SHARED_ROOT="/opt/lok/shared"
SHARED_DATA="$SHARED_ROOT/data"
SHARED_TENANTS="$SHARED_DATA/tenants"
SHARED_DB="$SHARED_DATA/app.db"
SHARED_KEYS="$SHARED_ROOT/config/api_keys.txt"

mkdir -p "$SHARED_TENANTS" "$SHARED_ROOT/config"

python3 - <<'PY'
import json
import os
import shutil
import sqlite3

old_base = "/opt/lok/releases/20260403-103504"
new_base = "/opt/lok/releases/20260408-185629"
shared = "/opt/lok/shared"
shared_data = os.path.join(shared, "data")
shared_tenants = os.path.join(shared_data, "tenants")
os.makedirs(shared_tenants, exist_ok=True)

old_db = os.path.join(old_base, "data", "app.db")
new_db = os.path.join(new_base, "data", "app.db")
shared_db = os.path.join(shared_data, "app.db")

shutil.copy2(old_db, shared_db)

src = sqlite3.connect(new_db)
src.row_factory = sqlite3.Row
dst = sqlite3.connect(shared_db)
dst.row_factory = sqlite3.Row
for row in src.execute(
    "select tenant_id, tenant_name, admin_username, admin_password_hash, enabled, created_at "
    "from tenants where tenant_id = ?",
    ("test_0001",),
):
    tenant_id = row["tenant_id"]
    if dst.execute("select 1 from tenants where tenant_id = ?", (tenant_id,)).fetchone():
        continue
    final_admin = row["admin_username"]
    if dst.execute("select 1 from tenants where admin_username = ?", (final_admin,)).fetchone():
        final_admin = f"{tenant_id}_admin"
    dst.execute(
        "insert into tenants (tenant_id, tenant_name, admin_username, admin_password_hash, enabled, created_at) "
        "values (?, ?, ?, ?, ?, ?)",
        (
            tenant_id,
            row["tenant_name"],
            final_admin,
            row["admin_password_hash"],
            row["enabled"],
            row["created_at"],
        ),
    )
dst.commit()
src.close()
dst.close()

for base in [os.path.join(old_base, "data", "tenants"), os.path.join(new_base, "data", "tenants")]:
    if not os.path.isdir(base):
        continue
    for name in os.listdir(base):
        src_dir = os.path.join(base, name)
        dst_dir = os.path.join(shared_tenants, name)
        if os.path.isdir(src_dir) and not os.path.exists(dst_dir):
            shutil.copytree(src_dir, dst_dir)

green = {
    "bg": "#f8fafc",
    "bg_soft": "#f0fdf4",
    "surface": "rgba(255, 255, 255, 0.96)",
    "surface_strong": "#ffffff",
    "line": "#dbe7df",
    "text": "#0f172a",
    "muted": "#64748b",
    "accent": "#10b981",
    "accent_strong": "#059669",
    "accent_soft": "#ecfdf5",
    "warm": "#f59e0b",
    "warm_soft": "rgba(245, 158, 11, 0.16)",
    "danger": "#ef4444",
    "primary": "#10b981",
    "primary_deep": "#059669",
    "primary_soft": "#ecfdf5",
}
for tenant_id in ["default", "test_0001"]:
    path = os.path.join(shared_tenants, tenant_id, "app_config.json")
    if not os.path.exists(path):
        continue
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    theme = data.get("theme") or {}
    theme.update(green)
    data["theme"] = theme
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

conn = sqlite3.connect(shared_db)
print(conn.execute("select tenant_id, tenant_name, admin_username from tenants order by id").fetchall())
conn.close()
PY

if [[ -f "$OLD_RELEASE/config/api_keys.txt" ]]; then
  cp -f "$OLD_RELEASE/config/api_keys.txt" "$SHARED_KEYS"
fi

rm -f "$CURRENT_LINK/data/app.db" "$CURRENT_LINK/data/app.db-shm" "$CURRENT_LINK/data/app.db-wal"
rm -rf "$CURRENT_LINK/data/tenants" "$CURRENT_LINK/config/api_keys.txt"
ln -sfn "$SHARED_DB" "$CURRENT_LINK/data/app.db"
ln -sfn "$SHARED_TENANTS" "$CURRENT_LINK/data/tenants"
ln -sfn "$SHARED_KEYS" "$CURRENT_LINK/config/api_keys.txt"

systemctl restart lok
sleep 4

echo "CURRENT=$(readlink -f $CURRENT_LINK)"
echo "PID=$(systemctl show -p MainPID --value lok)"
pwdx "$(systemctl show -p MainPID --value lok)"
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect("/opt/lok/shared/data/app.db")
print(conn.execute("select tenant_id, tenant_name, admin_username from tenants order by id").fetchall())
conn.close()
PY
curl -i -s http://127.0.0.1:6090/api/admin/tenants -H "Authorization: Bearer YWRtaW46cmFnMjAyNg==" | sed -n '1,20p'

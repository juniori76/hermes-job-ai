import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.0.123', username='eduardo', password='edu159753')

cmd = """python3 - << 'EOF'
import sqlite3
conn = sqlite3.connect('/home/eduardo/hermes-job-ai/data/hermes.db')
c = conn.cursor()
c.execute("SELECT count(*) FROM jobs")
print("Jobs count:", c.fetchone()[0])
c.execute("SELECT id, title, status FROM jobs LIMIT 10")
for row in c.fetchall():
    print(row)
EOF"""

stdin, stdout, stderr = ssh.exec_command(cmd)
print("STDOUT:", stdout.read().decode())
print("STDERR:", stderr.read().decode())
ssh.close()

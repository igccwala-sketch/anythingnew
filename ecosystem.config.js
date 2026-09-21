module.exports = {
  apps: [{
    name: 'gmail-creator',
    script: '/root/gmail_creator/venv/bin/python3',
    args: '/root/gmail_creator/bot.py',
    cwd: '/root/gmail_creator',
    interpreter: 'none',
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      PYTHONUNBUFFERED: '1'
    },
    log_file: '/root/gmail_creator/logs/bot.log',
    out_file: '/root/gmail_creator/logs/out.log',
    error_file: '/root/gmail_creator/logs/error.log'
  }]
}
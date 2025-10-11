module.exports = {
  apps : [{
    name: 'cian-frontend',
    script: 'npm',
    args: 'run dev',
    env: {
      PORT: 3005,
      NODE_ENV: 'development'
    },
    max_restarts: 10,
    min_uptime: '10s',
    autorestart: true,
    watch: false
  }]
}

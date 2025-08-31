#crontab ops/cronjobs.sh



# Run learner every 5 min
*/5 * * * * cd /opt/ecodiaos && /opt/ecodiaos/venv/bin/python -m workers.equor_learner >> /var/log/equor_learner.log 2>&1

# Run promoter every 5 min, offset by 2 min
2-59/5 * * * * cd /opt/ecodiaos && /opt/ecodiaos/venv/bin/python -m workers.promoter >> /var/log/equor_promoter.log 2>&1

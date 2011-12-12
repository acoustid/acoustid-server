#!/bin/sh

set -e

DATA_DIR=/home/acoustid/data

# synchronize backups
echo >> /var/log/acoustid/backup.log
date >> /var/log/acoustid/backup.log
rsync -av --delete --delete-after --fuzzy -e \
	"ssh -i /home/acoustid/.ssh/backup" \
	$DATA_DIR/ backup.acoustid.org:$DATA_DIR/ \
	>> /var/log/acoustid/backup.log


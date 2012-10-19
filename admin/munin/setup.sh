#!/bin/sh

cd `dirname $0`
dir=`pwd`

if [ -z "$1" ]
then
	echo "usage: setup.sh munin_plugin_path"
	exit 1
fi

ln -fvs $dir/plugin_wrapper.sh $1/acoustid_lookups
ln -fvs $dir/plugin_wrapper.sh $1/acoustid_lookup_time


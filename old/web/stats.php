<?php

include "lib/init.php";
include "lib/StatsUtils.php";

$title = "Statistics";
//$applications = ApplicationData::findByAccountId($g_user['id']);
$select = $g_db->select()
	->from('account', array('name', 'mbuser', 'submission_count'))
	->where('submission_count > 0')
	->order(array('submission_count DESC', 'name'));
$users = $g_db->fetchAll($select);

$submissions_url = StatsUtils::get_graph_url('submission.all', 60);
$fingerprints_url = StatsUtils::get_graph_url('fingerprint.all', 60);

$last_stats = StatsUtils::get_last_stats();
$stats = array();
$stats['Submissions'] = $last_stats['submission.all'] . ' (' . $last_stats['submission.unhandled'] . ' queued)';
$stats['Tracks'] = $last_stats['track.all'];
$stats['Unique MBIDs'] = $last_stats['track_mbid.unique'];
$stats['Fingerprints'] = $last_stats['fingerprint.all'];
$stats['Active users'] = $last_stats['account.active'];

include "tpl/stats.php";

?>

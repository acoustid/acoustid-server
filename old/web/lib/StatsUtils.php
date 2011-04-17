<?php

$EXTENDED_MAP = array(
	'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L',
	'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X',
	'Y', 'Z', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 
	'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v',
	'w', 'x', 'y', 'z', '0', '1', '2', '3', '4', '5', '6', '7', 
	'8', '9', '-', '.'
);
$EXTENDED_MAP_LENGTH = 64;

class StatsUtils {

	function encode_number($n, $max) {
		$n = intval(61 * $n / $max);
		if ($n <= 25) {
			return chr(ord('A') + $n);
		}
		elseif ($n <= 51) {
			$n -= 26;
			return chr(ord('a') + $n);
		}
		else {
			$n -= 52;
			return chr(ord('0') + $n);
		}
	}

	function encode_number_e($n, $max) {
		global $EXTENDED_MAP_LENGTH, $EXTENDED_MAP;
		$n = intval($EXTENDED_MAP_LENGTH * $EXTENDED_MAP_LENGTH * $n / $max);
		if ($n > $EXTENDED_MAP_LENGTH * $EXTENDED_MAP_LENGTH - 1) {
			return "..";
		}
		elseif ($n < 0) {
			return "__";
		}
		else {
			$quotient = intval($n / $EXTENDED_MAP_LENGTH);
			$remainder = $n - $EXTENDED_MAP_LENGTH * $quotient;
			return $EXTENDED_MAP[$quotient] . $EXTENDED_MAP[$remainder];
		}
	}

	public function get_last_stats() {
		global $g_db;

		$values = array();
		$rows = $g_db->fetchAll("SELECT name, value FROM stats WHERE date = (SELECT max(date) FROM stats)");
		foreach ($rows as $row) {
			$values[$row['name']] = $row['value'];
		}
		return $values;
	}

public function get_graph_url($name, $num_days=40) {
	global $g_db;

	$select = $g_db->select()
		->from('stats', array('date', 'value'))
		->where('name = ?', $name)
		->order(array('date DESC'))->limit($num_days + 5);
	$values = array();
	$rows = $g_db->fetchAll($select);
	foreach ($rows as $row) {
		$values[$row['date']] = $row['value'];
	}

	$dates = array();
	$labels = array();

	$date = new DateTime();
	$one_day = new DateInterval("P1D");
	for ($i = 0; $i < $num_days; $i++) {
		$dates[] = $date->format('Y-m-d');
		if ($i % 5 == 0) {
			$labels[] = $date->format('d/m');
		}
		$date->sub($one_day);
	}
	$labels = array_reverse($labels);

	$max_value = max(array_values($values));
	$max_value += floor(0.1 * $max_value);
	$data = "";
	for ($i = 0; $i < $num_days; $i++) {
		$value = $values[$dates[$num_days - $i - 1]];
		$data .= is_null($value) ? "_" : self::encode_number_e($value, $max_value);
	}

	return "http://chart.apis.google.com/chart" .
	   "?chxl=1:|" . implode("|", $labels) . 
	   "&chxr=0,0,$max_value" . 
	   "&chxt=y,x" . 
	   "&chs=460x150" .
	   "&cht=lc" .
	   "&chco=3D7930" .
	   "&chd=e:$data" .
	   "&chg=7.15,-1,1,0" .
	   "&chm=B,C5D4B5BB,0,0,0";
}

}

?>

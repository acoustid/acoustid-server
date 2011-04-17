<?php

include "lib/config.php";
include "lib/UserData.php";
include "Zend/Db.php";

session_start();

function redirect($path='') {
	global $cfg_base_url;
	if (strpos($path, "http") === 0) {
		$url = $path;
	}
	else {
		$url = "${cfg_base_url}${path}";
	}
	header("Location: $url");
	exit(0);
}


$g_db = Zend_Db::factory('Pdo_Pgsql', array(
    'host'     => $cfg_db_host,
	'port'     => 5432,
    'username' => $cfg_db_user,
    'password' => $cfg_db_password,
    'dbname'   => $cfg_db_name
));

if (isset($_SESSION['user'])) {
	$id = intval($_SESSION['user']);
	$g_user = UserData::getById($id);
}
else {
	$g_user = null;
}

?>

<?php

include "lib/init.php";
include "lib/ApplicationData.php";

if (!$g_user) {
	redirect("login");
}

$title = "Your Applications";
$applications = ApplicationData::findByAccountId($g_user['id']);

include "tpl/applications.php";

?>

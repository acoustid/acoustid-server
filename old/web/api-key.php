<?php

include "lib/init.php";

if (!$g_user) {
	redirect("login");
}

$title = "Your API Key";
$api_key = $g_user['apikey'];

include "tpl/api-key.php";

?>

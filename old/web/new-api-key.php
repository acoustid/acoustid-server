<?php

include "lib/init.php";

if (!$g_user) {
	redirect("login");
}

UserData::updateApiKey($g_user['id']);
redirect("api-key");

?>

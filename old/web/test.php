<?php

include "lib/init.php";
include "lib/openid.php";

$consumer = new LightOpenID();
$consumer->identity = 'https://me.yahoo.com';
$consumer->required = array('namePerson/friendly');
echo $consumer->authUrl();

?>

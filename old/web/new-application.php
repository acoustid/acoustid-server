<?php

include "lib/init.php";
include "lib/ApplicationData.php";

if (!$g_user) {
	redirect("login");
}

$error = '';

if (isset($_POST['submit'])) {

	$name = $_POST['name'];
	$version = $_POST['version'];
	if ($name && $version) {
		try {
			ApplicationData::insert(array(
				'name'       => $name,
				'version'    => $version,
				'account_id' => $g_user['id'],
			));
			redirect('applications');
		}
		catch (Exception $e) {
			$error = 'Error while registering the application';
		}
	}
	elseif (!$name) {
		$error = 'Missing application name';
	}
	elseif (!$version) {
		$error = 'Missing version number';
	}

}

$title = "New Application";

include "tpl/new-application.php";

?>

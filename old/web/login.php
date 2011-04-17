<?php

include "lib/init.php";
include "lib/openid.php";

function checkMusicBrainzAccount($username, $password) {
	$wsurl = "http://musicbrainz.org/ws/1/user?type=xml&name=" . urlencode($username);
	$sess = curl_init();
	curl_setopt($sess, CURLOPT_URL, $wsurl);
	curl_setopt($sess, CURLOPT_HTTPAUTH, CURLAUTH_DIGEST); 
	curl_setopt($sess, CURLOPT_USERPWD, "$username:$password");
	curl_setopt($sess, CURLOPT_RETURNTRANSFER, TRUE);
	curl_setopt($sess, CURLOPT_CONNECTTIMEOUT, 5);
	$data = curl_exec($sess);
	$code = curl_getinfo($sess, CURLINFO_HTTP_CODE);
	curl_close($sess);
	return ($code == 200);
}

$errors = array('openid' => '', 'mb' => '');

if (isset($_POST['login'])) {

	if ($_POST['login'] == 'openid') {
		$openid = $_POST['openid_identifier'];
		if ($openid) {
			try {
				$consumer = new LightOpenID();
				$consumer->identity = $openid;
				$consumer->optional = array('namePerson/friendly');
				redirect($consumer->authUrl());
			}
			catch (ErrorException $e) {
				$errors['openid'] = 'Error while trying to verify the OpenID';
			}
		}
		else {
			$errors['openid'] = 'Missing OpenID';
		}
	}

	elseif ($_POST['login'] == 'mb') {
		$username = $_POST['mb_user'];
		$password = $_POST['mb_password'];
		if ($username && $password) {
			if (checkMusicBrainzAccount($username, $password)) {
				$user = UserData::getByMusicBrainzName($username);
				if (!$user) {
					$id = UserData::insert(array(
						'name'   => $username,
						'mbuser' => $username,
					));
				}
				else {
					$id = $user['id'];
					UserData::updateLastLoginDate($id);
				}
				$_SESSION['user'] = $id;
				redirect('api-key');
			}
			else {
				$errors['mb'] = 'Invalid username or password';
			}
		}
		elseif (!$username) {
			$errors['mb'] = 'Missing username';
		}
		elseif (!$password) {
			$errors['mb'] = 'Missing password';
		}
	}

}

elseif (isset($_GET['openid_mode'])) {
    if ($_GET['openid_mode'] == "id_res") {
		$consumer = new LightOpenID();
		if ($consumer->validate()) {
			$openid = $consumer->identity;
			$attributes = $consumer->getAttributes();
			$name = 'OpenID User';
			if ($attributes['namePerson/friendly']) {
				$name = $attributes['namePerson/friendly'];
			}
			$user = UserData::getByOpenId($openid);
			if (!$user) {
				$id = UserData::insertWithOpenId(array(
					'name' => $name,
				), $openid);
			}
			else {
				$id = $user['id'];
				UserData::updateLastLoginDate($id);
			}
			$_SESSION['user'] = $id;
			redirect('api-key');
        }
		else {
			$errors['openid'] = 'Invalid OpenID';
        }
    }
	elseif ($_GET['openid_mode'] == "cancel") {
		$errors['openid'] = 'OpenID verification has been cancelled';
    }
}

$title = "Log In";

include "tpl/login.php";

?>

<?php include "header.php"; ?>

<script type="text/javascript">
var providers = {
	'google': 'https://www.google.com/accounts/o8/id',
	'yahoo': 'https://me.yahoo.com',
	'flickr': 'http://www.flickr.com/username',
	'myspace': 'http://myspace.com',
	'aol': 'http://openid.aol.com',
	'wordpress': 'http://username.wordpress.com',
	'livejournal': 'http://username.livejournal.com',
	'launchpad': 'http://login.launchpad.net/+openid',
}
function setOpenIdUrl(provider) {
	document.getElementsByName('openid_identifier')[0].value = providers[provider];
}
</script>

<h2>Log in With OpenID</h2>
<?php if ($errors['openid']) { ?>
<p class="errors"><?= htmlspecialchars($errors['openid']) ?></p>
<?php } ?>
<form action="<?= $cfg_https_base_url ?>login" method="POST">
<small>Use
			<a href="javascript:setOpenIdUrl('google');">Google</a>,
			<a href="javascript:setOpenIdUrl('yahoo');">Yahoo!</a>,
			<a href="javascript:setOpenIdUrl('myspace');">MySpace</a>,
			<a href="javascript:setOpenIdUrl('wordpress');">WordPress</a>,
			<a href="javascript:setOpenIdUrl('livejournal');">LiveJournal</a> or enter an OpenID URL:
		</small><br />
<input name="openid_identifier" type="text" class="openid" /> <input type="submit" value="Log in" /><br />
<input type="hidden" name="login" value="openid" />
</form>
<br />

<h2>Log in With a MusicBrainz Account</h2>
<?php if ($errors['mb']) { ?>
<p class="errors"><?= htmlspecialchars($errors['mb']) ?></p>
<?php } ?>
<form action="<?= $cfg_https_base_url ?>login" method="POST">
<p>
	<small><label for="mb_user_i">Enter your MusicBrainz user name:</label></small><br />
	<input name="mb_user" id="mb_user_i" type="text" class="text" /><br />
	<small><label for="mb_password_i">And your MusicBrainz password:</label> <em>(please read <a href="http://wiki.acoustid.org/wiki/FAQ">FAQ</a>)</em></small><br />
	<input name="mb_password" id="mb_password_i" type="password" class="text" />
</p>
<p>
	<input type="submit" value="Log in" />
	<input type="hidden" name="login" value="mb" />
</p>
</form>

<?php include "footer.php"; ?>

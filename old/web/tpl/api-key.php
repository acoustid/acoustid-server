<?php include "header.php"; ?>

<h2><?= htmlspecialchars($title) ?></h2>

<p>
	Your API key is a token the Acoustid web service uses to identify yourself when you submit
	fingerprints. The following key can be used in any Acoustid-enabled application:
</p>

<p class="center">
	<code style="padding: 0.4em; border: solid 1px #b2b2b2; font-size: 140%;"><?= htmlspecialchars($api_key) ?></code>
</p>

<p class="center">
	<a href="<?= $cfg_base_url ?>new-api-key">Generate a new API key</a>
</p>

<?php include "footer.php"; ?>

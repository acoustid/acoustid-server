<?php include "header.php"; ?>

<h2><?= htmlspecialchars($title) ?></h2>

<?php if ($error) { ?>
<p class="errors"><?= htmlspecialchars($error) ?></p>
<?php } ?>
<form action="/new-application" method="POST">
<p>
	<small><label for="name_i">Application name:</label></small><br />
 	<input name="name" id="name_i" type="text" class="text" /><br />
	<small><label for="version_i">Version number:</label></small><br />
	<input name="version" id="version_i" type="text" class="text" />
</p>
<p>
	<input type="submit" value="Register" />
	<input type="hidden" name="submit" value="1" />
</p>
</form>

<?php include "footer.php"; ?>

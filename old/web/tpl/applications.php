<?php include "header.php"; ?>

<h2><?= htmlspecialchars($title) ?></h2>

<?php if ($applications) { ?>
<p>
	If you are the developer of an application that uses the Acoustid web service, please register your application.
	So far you've registered the following applications:
</p>
<?php } else { ?>
<p>
	You do not have any registered applications. If you are the developer of an application that uses the Acoustid web service, please register your application.
</p>
<?php } ?>

<table class="apps">
<thead>
	<tr>
		<th>Name</th>
		<th>Version</th>
		<th>API Key</th>
	</tr>
</thead>
<tbody>
<?php foreach ($applications as $app) { ?>
	<tr>
		<td><?= htmlspecialchars($app['name']) ?></td>
		<td><?= htmlspecialchars($app['version']) ?></td>
		<td><code><?= htmlspecialchars($app['apikey']) ?></code></td>
	</tr>
<?php } ?>
</tbody>
</table>

<p class="center">
	<a href="<?= $cfg_base_url ?>new-application">Register a new application</a>
</p>

<?php include "footer.php"; ?>

<?php include "header.php"; ?>

<h2><?= htmlspecialchars($title) ?></h2>

<h3>Overview</h3>
<table class="apps">
<thead>
	<tr>
		<th>Name</th>
		<th>Count</th>
	</tr>
</thead>
<tbody>
<?php foreach ($stats as $text => $value) { ?>
	<tr>
		<td><?= htmlspecialchars($text) ?></td>
		<td><?= htmlspecialchars($value) ?></td>
	</tr>
<?php } ?>
</tbody>
</table>
<br />

<h3>Submissions</h3>
<p><img src="<?= htmlspecialchars($submissions_url) ?>" /></p>

<h3>Fingerprints</h3>
<p><img src="<?= htmlspecialchars($fingerprints_url) ?>" /></p>

<h3>Top users</h3>

<table class="apps">
<thead>
	<tr>
		<th>Name</th>
		<th>All submissions (incl. duplicates)</th>
	</tr>
</thead>
<tbody>
<?php foreach ($users as $user) { ?>
	<tr>
		<td><?php if ($user['mbuser']) { echo '<a href="http://musicbrainz.org/show/user/?username=' . htmlspecialchars($user['mbuser']) . '">'; } ?>
			<?= htmlspecialchars($user['name']) ?>
		<?php if ($user['mbuser']) { echo '</a>'; } ?></td>
		<td><?= htmlspecialchars($user['submission_count']) ?></td>
	</tr>
<?php } ?>
</tbody>
</table>

<?php include "footer.php"; ?>

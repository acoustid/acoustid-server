<?php

class ApplicationData {

	public static function insert($data) {
		global $g_db;
		$data['apikey'] = new Zend_Db_Expr('generate_api_key()');
		$g_db->insert('application', $data);
		return $g_db->lastInsertId('application', 'id');
	}

	public static function findByAccountId($account_id) {
		global $g_db;
		$select = $g_db->select()
			->from('application')
			->where('account_id = ?', $account_id)
			->where('active = true')
			->order(array('name', 'version'));
		return $g_db->fetchAll($select);
	}

}

?>

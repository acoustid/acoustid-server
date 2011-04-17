<?php

class UserData {

	public static function insert($data) {
		global $g_db;
		$data['apikey'] = new Zend_Db_Expr('generate_api_key()');
		$data['lastlogin'] = new Zend_Db_Expr('current_timestamp');
		$g_db->insert('account', $data);
		return $g_db->lastInsertId('account', 'id');
	}

	public static function insertWithOpenId($data, $openid) {
		global $g_db;
		$g_db->beginTransaction();
		try {
			$id = self::insert($data);
			$g_db->insert('account_openid', array(
				'openid'     => $openid,
				'account_id' => $id,
			));
			$g_db->commit();
		}
		catch (Exception $e) {
			$g_db->rollBack();
			throw $e;
		}
		return $id;
	}

	public static function updateApiKey($id) {
		global $g_db;
		$data = array(
			'apikey' => new Zend_Db_Expr('generate_api_key()')
		);
		$g_db->update('account', $data, array('id = ?' => $id));
	}

	public static function updateLastLoginDate($id) {
		global $g_db;
		$data = array(
			'lastlogin' => new Zend_Db_Expr('current_timestamp')
		);
		$g_db->update('account', $data, array('id = ?' => $id));
	}

	public static function getById($id) {
		global $g_db;
		$select = $g_db->select()
			->from('account')
			->where('id = ?', $id);
		return $g_db->fetchRow($select);
	}

	public static function getByMusicBrainzName($username) {
		global $g_db;
		$select = $g_db->select()
			->from('account')
			->where('lower(mbuser) = lower(?)', $username);
		return $g_db->fetchRow($select);
	}

	public static function getByOpenId($openid) {
		global $g_db;
		$select = $g_db->select()
			->from('account_openid', array())
			->join('account', 'account.id=account_openid.account_id')
			->where('openid = ?', $openid);
		return $g_db->fetchRow($select);
	}

}

?>

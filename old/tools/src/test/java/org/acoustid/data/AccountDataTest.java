// Acoustid -- Audio fingerprint lookup server
// Copyright (C) 2010  Lukas Lalinsky
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.

package org.acoustid.data;

import org.acoustid.data.sql.SQLAccountData;
import org.acoustid.test.DatabaseTestCase;
import org.junit.Test;
import static org.junit.Assert.*;
import java.sql.Connection;
import java.sql.SQLException;
import org.acoustid.Account;

public class AccountDataTest extends DatabaseTestCase {

    @Test
    public void testFindByApiKey() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO account (name, apikey) VALUES ('name', 'key')");
        SQLAccountData accountData = new SQLAccountData();
        accountData.setConnection(connection);
        Account account1 = accountData.findByApiKey("key");
        assertEquals(1, account1.getId());
        assertEquals("name", account1.getName());
        Account account2 = accountData.findByApiKey("key-does-not-exist");
        assertNull(account2);
    }

}

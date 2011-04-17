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

import org.acoustid.data.sql.SQLSourceData;
import org.acoustid.test.DatabaseTestCase;
import org.junit.Test;
import static org.junit.Assert.*;
import java.sql.Connection;
import java.sql.SQLException;
import org.acoustid.Source;

public class SourceDataTest extends DatabaseTestCase {

    @Test
    public void testFindOrInsert() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO account (name, apikey) VALUES ('accname', 'acckey')");
        runSql(connection, "INSERT INTO account (name, apikey) VALUES ('accname2', 'acckey2')");
        runSql(connection, "INSERT INTO application (name, version, apikey, account_id) VALUES ('appname', '1.0', 'appkey', 1)");
        runSql(connection, "INSERT INTO application (name, version, apikey, account_id) VALUES ('appname2', '1.0', 'appkey2', 2)");
        runSql(connection, "INSERT INTO source (application_id, account_id) VALUES (1, 1)");
        connection.commit();
        SQLSourceData sourceData = new SQLSourceData();
        sourceData.setConnection(connection);
		// Existing
        Source source = sourceData.findOrInsert(1, 1);
        assertEquals(1, source.getId());
        assertEquals(1, source.getApplicationId());
        assertEquals(1, source.getAccountId());
		// Newly created
        Source source2 = sourceData.findOrInsert(1, 2);
        assertEquals(2, source2.getId());
        assertEquals(1, source2.getApplicationId());
        assertEquals(2, source2.getAccountId());
		// Newly created
        Source source3 = sourceData.findOrInsert(2, 1);
        assertEquals(3, source3.getId());
        assertEquals(2, source3.getApplicationId());
        assertEquals(1, source3.getAccountId());
    }

    @Test
    public void testFind() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO account (name, apikey) VALUES ('accname', 'acckey')");
        runSql(connection, "INSERT INTO application (name, version, apikey, account_id) VALUES ('appname', '1.0', 'appkey', 1)");
        runSql(connection, "INSERT INTO source (application_id, account_id) VALUES (1, 1)");
        SQLSourceData sourceData = new SQLSourceData();
        sourceData.setConnection(connection);
        Source source = sourceData.find(1, 1);
        assertEquals(1, source.getId());
        assertEquals(1, source.getApplicationId());
        assertEquals(1, source.getAccountId());
        Source source2 = sourceData.find(2, 2);
        assertNull(source2);
    }

    @Test
    public void testInsert() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO account (name, apikey) VALUES ('accname', 'acckey')");
        runSql(connection, "INSERT INTO application (name, version, apikey, account_id) VALUES ('appname', '1.0', 'appkey', 1)");
        SQLSourceData sourceData = new SQLSourceData();
        sourceData.setConnection(connection);
        Source source = new Source();
		source.setApplicationId(1);
		source.setAccountId(1);
		sourceData.insert(source);
        assertEquals(1, source.getId());
        Source source2 = sourceData.find(1, 1);
        assertEquals(1, source2.getId());
        assertEquals(1, source2.getApplicationId());
        assertEquals(1, source2.getAccountId());
    }

}

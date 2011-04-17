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

import org.acoustid.data.sql.SQLApplicationData;
import org.acoustid.test.DatabaseTestCase;
import org.junit.Test;
import static org.junit.Assert.*;
import java.sql.Connection;
import java.sql.SQLException;
import org.acoustid.Application;

public class ApplicationDataTest extends DatabaseTestCase {

    @Test
    public void testFindByApiKey() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO account (name, apikey) VALUES ('name', 'key')");
        runSql(connection, "INSERT INTO application (name, version, apikey, account_id) VALUES ('name', '1.0', 'key', 1)");
        SQLApplicationData applicationData = new SQLApplicationData();
        applicationData.setConnection(connection);
        Application application1 = applicationData.findByApiKey("key");
        assertEquals(1, application1.getId());
        assertEquals("name", application1.getName());
        Application application2 = applicationData.findByApiKey("key-does-not-exist");
        assertNull(application2);
    }

}

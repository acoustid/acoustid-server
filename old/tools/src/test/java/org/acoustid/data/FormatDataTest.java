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

import org.acoustid.data.sql.SQLFormatData;
import org.acoustid.test.DatabaseTestCase;
import org.junit.Test;
import static org.junit.Assert.*;
import java.sql.Connection;
import java.sql.SQLException;
import org.acoustid.Format;

public class FormatDataTest extends DatabaseTestCase {

    @Test
    public void testFindOrInsert() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO format (name) VALUES ('FLAC')");
        SQLFormatData formatData = new SQLFormatData();
        formatData.setConnection(connection);
        Format format = formatData.findOrInsert("FLAC");
        assertEquals(1, format.getId());
        assertEquals("FLAC", format.getName());
        Format format2 = formatData.findOrInsert("MP5");
        assertEquals(2, format2.getId());
        assertEquals("MP5", format2.getName());
    }

    @Test
    public void testFind() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO format (name) VALUES ('FLAC')");
        SQLFormatData formatData = new SQLFormatData();
        formatData.setConnection(connection);
        Format format = formatData.find("FLAC");
        assertEquals(1, format.getId());
        assertEquals("FLAC", format.getName());
        Format format2 = formatData.find("MP5");
        assertNull(format2);
    }

    @Test
    public void testInsert() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        SQLFormatData formatData = new SQLFormatData();
        formatData.setConnection(connection);
        Format format = new Format();
		format.setName("MP5");
		formatData.insert(format);
        assertEquals(1, format.getId());
        Format format2 = formatData.find("MP5");
        assertEquals(1, format2.getId());
        assertEquals("MP5", format2.getName());
    }

}

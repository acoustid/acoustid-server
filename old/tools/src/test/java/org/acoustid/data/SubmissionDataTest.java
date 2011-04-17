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

import org.acoustid.test.DatabaseTestCase;
import org.junit.Test;
import static org.junit.Assert.*;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.List;
import org.acoustid.Submission;
import org.acoustid.data.sql.SQLSubmissionData;

public class SubmissionDataTest extends DatabaseTestCase {

    @Test
    public void testFindUnhandled() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO account (name, apikey) VALUES ('accname', 'acckey')");
        runSql(connection, "INSERT INTO application (name, version, apikey, account_id) VALUES ('appname', '1.0', 'appkey', 1)");
        runSql(connection, "INSERT INTO source (application_id, account_id) VALUES (1, 1)");
        runSql(connection, "INSERT INTO submission (source_id, fingerprint, length, mbid) VALUES (1, '{1,2,3}', 22, 'dc03039c-efd4-4e51-aac0-b25cfc90e6d5')");
        runSql(connection, "INSERT INTO submission (source_id, fingerprint, length, puid) VALUES (1, '{3,4,5}', 33, 'e9b0a4fc-dd47-441e-8603-04f698828653')");
        connection.commit();
        SQLSubmissionData submissionData = new SQLSubmissionData();
        submissionData.setConnection(connection);
		// Existing
        List<Submission> results = submissionData.findUnhandled(10);
        assertEquals(2, results.size());
        assertEquals(1, results.get(0).getId());
        assertEquals("dc03039c-efd4-4e51-aac0-b25cfc90e6d5", results.get(0).getMBID());
        assertEquals(null, results.get(0).getPUID());
        assertEquals(2, results.get(1).getId());
        assertEquals(null, results.get(1).getMBID());
        assertEquals("e9b0a4fc-dd47-441e-8603-04f698828653", results.get(1).getPUID());
    }

    @Test
    public void testFindUnhandledNewFirst() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO account (name, apikey) VALUES ('accname', 'acckey')");
        runSql(connection, "INSERT INTO application (name, version, apikey, account_id) VALUES ('appname', '1.0', 'appkey', 1)");
        runSql(connection, "INSERT INTO source (application_id, account_id) VALUES (1, 1)");
        runSql(connection, "INSERT INTO submission (source_id, fingerprint, length, mbid) VALUES (1, '{1,2,3}', 22, 'dc03039c-efd4-4e51-aac0-b25cfc90e6d5')");
        runSql(connection, "INSERT INTO submission (source_id, fingerprint, length, mbid) VALUES (1, '{3,4,5}', 33, 'e9b0a4fc-dd47-441e-8603-04f698828653')");
        runSql(connection, "INSERT INTO track (id) VALUES (nextval('track_id_seq'))");
        runSql(connection, "INSERT INTO track_mbid (track_id, mbid) VALUES (1, 'dc03039c-efd4-4e51-aac0-b25cfc90e6d5')");
        connection.commit();
        SQLSubmissionData submissionData = new SQLSubmissionData();
        submissionData.setConnection(connection);
		// Existing
        List<Submission> results = submissionData.findUnhandled(10);
        assertEquals(1, results.size());
        assertEquals(2, results.get(0).getId());
        assertEquals("e9b0a4fc-dd47-441e-8603-04f698828653", results.get(0).getMBID());
        assertEquals(null, results.get(0).getPUID());
    }

}

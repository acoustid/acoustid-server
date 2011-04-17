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

package org.acoustid.test;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;

public class DatabaseTestCase {

    public DatabaseTestCase() {
    }

    protected void runSql(Connection connection, String sql) throws SQLException {
        Statement statement = connection.createStatement();
        statement.execute(sql);
        connection.commit();
    }

    protected Connection setUpDatabase() throws SQLException, ClassNotFoundException {
        Class.forName("org.postgresql.Driver");
        Connection connection = DriverManager.getConnection("jdbc:postgresql://127.0.0.1/acoustid_test", "acoustid", "acoustid");
        Statement statement = connection.createStatement();
		String[] sequences = new String[] {
			"account_id_seq",
			"application_id_seq",
			"fingerprint_id_seq",
			"format_id_seq",
			"track_id_seq",
			"source_id_seq",
			"submission_id_seq",
		};
        statement.execute("TRUNCATE submission, account_openid, track_mbid, fingerprint, track, source, application, account, format");
		for (String sequence: sequences) {
	        statement.execute("ALTER SEQUENCE " + sequence + " RESTART WITH 1");
		}
        connection.commit();
        return connection;
    }

}

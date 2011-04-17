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

package org.acoustid.data.sql;

import com.google.inject.Inject;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import org.acoustid.Source;
import org.acoustid.data.SourceData;

public class SQLSourceData extends Data implements SourceData {

    private static final String SELECT_SQL =
        "SELECT id FROM source WHERE application_id = ? AND account_id = ?";

    private static final String INSERT_SQL =
        "INSERT INTO source (application_id, account_id) VALUES (?, ?) RETURNING id";

    @Override
    public Source findOrInsert(int applicationId, int accountId) throws SQLException {
        Source source = find(applicationId, accountId);
        if (source == null) {
            source = new Source();
            source.setApplicationId(applicationId);
            source.setAccountId(accountId);
            insert(source);
        }
        return source;
    }

    @Override
    public Source find(int applicationId, int accountId) throws SQLException {
        PreparedStatement statement = getConnection().prepareStatement(SELECT_SQL);
        statement.setInt(1, applicationId);
        statement.setInt(2, accountId);
        ResultSet rs = statement.executeQuery();
        while (rs.next()) {
            Source source = new Source();
            source.setId(rs.getInt("id"));
            source.setApplicationId(applicationId);
            source.setAccountId(accountId);
            statement.close();
            return source;
        }
        statement.close();
        return null;
    }

    @Override
    public void insert(Source source) throws SQLException {
        PreparedStatement statement = getConnection().prepareStatement(INSERT_SQL);
        statement.setInt(1, source.getApplicationId());
        statement.setInt(2, source.getAccountId());
        ResultSet rs = statement.executeQuery();
        rs.next();
        source.setId(rs.getInt(1));
        statement.close();
    }

}

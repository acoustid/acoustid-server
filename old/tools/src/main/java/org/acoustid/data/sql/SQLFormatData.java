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
import org.acoustid.Format;
import org.acoustid.data.FormatData;

public class SQLFormatData extends Data implements FormatData {

    private static final String SELECT_SQL =
        "SELECT id FROM format WHERE name = ?";

    private static final String INSERT_SQL =
        "INSERT INTO format (name) VALUES (?) RETURNING id";

    @Override
    public Format findOrInsert(String name) throws SQLException {
        Format format = find(name);
        if (format == null) {
            format = new Format();
            format.setName(name);
            insert(format);
        }
        return format;
    }

    @Override
    public Format find(String name) throws SQLException {
        PreparedStatement statement = getConnection().prepareStatement(SELECT_SQL);
        statement.setString(1, name);
        ResultSet rs = statement.executeQuery();
        while (rs.next()) {
            Format format = new Format();
            format.setId(rs.getInt("id"));
            format.setName(name);
            statement.close();
            return format;
        }
        statement.close();
        return null;
    }

    @Override
    public void insert(Format format) throws SQLException {
        PreparedStatement statement = getConnection().prepareStatement(INSERT_SQL);
        statement.setString(1, format.getName());
        ResultSet rs = statement.executeQuery();
        rs.next();
        format.setId(rs.getInt(1));
        statement.close();
    }

}

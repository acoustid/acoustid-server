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
import org.acoustid.Application;
import org.acoustid.data.ApplicationData;

public class SQLApplicationData extends Data implements ApplicationData {

    private static final String SELECT_BY_API_KEY_SQL =
        "SELECT id, name, version FROM application WHERE apikey = ?";

    @Override
    public Application findByApiKey(String apiKey) throws SQLException {
        PreparedStatement statement = getConnection().prepareStatement(SELECT_BY_API_KEY_SQL);
        statement.setString(1, apiKey);
        ResultSet rs = statement.executeQuery();
        while (rs.next()) {
            Application application = new Application();
            application.setId(rs.getInt("id"));
            application.setName(rs.getString("name"));
            application.setVersion(rs.getString("version"));
            application.setApiKey(apiKey);
            statement.close();
            return application;
        }
        statement.close();
        return null;
    }

}

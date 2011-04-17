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

package org.acoustid.server;

import com.mchange.v2.c3p0.ConnectionCustomizer;
import java.sql.Connection;
import java.sql.Statement;

public class DatabaseConnectionCustomizer implements ConnectionCustomizer {

    @Override
    public void onAcquire(Connection conn, String parentDataSourceIdentityToken) throws Exception {
        Statement stmt = conn.createStatement();
        stmt.execute("SET gin_fuzzy_search_limit TO 15");
        stmt.close();
    }

    @Override
    public void onDestroy(Connection conn, String string) throws Exception {
    }

    @Override
    public void onCheckOut(Connection conn, String string) throws Exception {
    }

    @Override
    public void onCheckIn(Connection conn, String string) throws Exception {
    }

}

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
import java.sql.SQLException;
import org.acoustid.data.DataException;
import org.acoustid.data.Transaction;

public class SQLTransaction implements Transaction {

    private Connection connection;

    @Inject
    public SQLTransaction(Connection connection) {
        this.connection = connection;
    }

    @Override
    public void commit() throws DataException {
        try {
            connection.commit();
        }
        catch (SQLException ex) {
            throw new DataException("Couldn't commit the transaction", ex);
        }
    }

    @Override
    public void rollback() throws DataException {
        try {
            connection.rollback();
        }
        catch (SQLException ex) {
            throw new DataException("Couldn't rollback the transaction", ex);
        }
    }

}

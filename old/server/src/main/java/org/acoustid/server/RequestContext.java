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

import com.google.inject.Inject;
import java.sql.SQLException;
import java.sql.Connection;
import org.apache.log4j.Logger;

public class RequestContext implements Context {

    private static final Logger logger = Logger.getLogger(RequestContext.class);
    private ApplicationContext context;
    private Connection connection = null;

    @Inject
    public RequestContext(ApplicationContext context) {
        this.context = context;
    }

    void close() {
        try {
            if (connection != null && !connection.isClosed()) {
                logger.debug("Closing database connection " + connection);
                connection.close();
            }
        }
        catch (SQLException ex) {
            logger.error("Failed to close a database connection", ex);
        }
    }

    @Override
    public Connection getConnection() throws SQLException {
        if (connection == null) {
            logger.debug("Requesting a new database connection");
            connection = context.getConnection();
        }
        return connection;
    }

    @Override
    public void incrementLookupCount() {
        context.incrementLookupCount();
    }

    @Override
    public void incrementSubmissionCount() {
        context.incrementSubmissionCount();
    }

    @Override
    public void incrementSuccessfulLookupCount() {
        context.incrementSuccessfulLookupCount();
    }

}

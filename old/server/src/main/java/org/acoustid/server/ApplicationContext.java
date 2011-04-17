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
import com.google.inject.Singleton;
import java.sql.SQLException;
import java.beans.PropertyVetoException;
import com.mchange.v2.c3p0.ComboPooledDataSource;
import java.sql.Connection;
import java.util.Properties;
import org.apache.commons.configuration.Configuration;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;
import org.apache.log4j.Logger;
import org.apache.log4j.PropertyConfigurator;

@Singleton
public class ApplicationContext implements Context {

    private static final Logger logger = Logger.getLogger(ApplicationContext.class);
    private Configuration config;
    private ComboPooledDataSource dataSource;
    private AtomicInteger lookupCount = new AtomicInteger();
    private AtomicInteger successfulLookupCount = new AtomicInteger();
    private AtomicInteger submissionCount = new AtomicInteger();

    @Inject
    public ApplicationContext(Configuration config) {
        this.config = config;
        dataSource = new ComboPooledDataSource();
        try {
            dataSource.setDriverClass("org.postgresql.Driver");
        }
        catch (PropertyVetoException e) {
            throw new RuntimeException("Couldn't load org.postgresql.Driver", e);   
        }
        dataSource.setIdleConnectionTestPeriod(30);
        dataSource.setPreferredTestQuery("SELECT 1");
        dataSource.setConnectionCustomizerClassName("org.acoustid.server.DatabaseConnectionCustomizer");
        dataSource.setAutoCommitOnClose(false);
        dataSource.setCheckoutTimeout(1000 * 10);
        prepareDataSource();
        configureLogging();
    }

    private void configureLogging() {
        Properties properties = new Properties();
        properties.setProperty("log4j.rootLogger", "INFO, stderr");
        properties.setProperty("log4j.appender.stderr", "org.apache.log4j.ConsoleAppender");
        properties.setProperty("log4j.appender.stderr.target", "System.err");
        properties.setProperty("log4j.appender.stderr.layout", "org.apache.log4j.PatternLayout");
        properties.setProperty("log4j.appender.stderr.layout.ConversionPattern", "%d{yy-dd-MM HH:mm:ss} [%t] %-5p %c %x - %m%n");
        properties.setProperty("log4j.logger.org.acoustid.SubmissionImporter", "DEBUG");
        //properties.setProperty("log4j.logger.com.mchange.v2", "DEBUG");
        //properties.setProperty("log4j.logger.org.acoustid", "DEBUG");
        PropertyConfigurator.configure(properties);
    }

    private void prepareDataSource() {
        String jdbcUrl = "jdbc:postgresql://" + config.getString("database.host");
        String port = config.getString("database.port");
        if (port != null) {
            jdbcUrl += ":" + port;
        }
        jdbcUrl += "/" + config.getString("database.name");
        logger.info("Connecting to database with URL " + jdbcUrl + " and user " + config.getString("database.user"));
        dataSource.setJdbcUrl(jdbcUrl);
        dataSource.setUser(config.getString("database.user"));
        dataSource.setPassword(config.getString("database.password"));
    }

    void close() {
        dataSource.close();
    }

    public DataSource getDataSource() {
        return dataSource;
    }

    @Override
    public Connection getConnection() throws SQLException {
        logger.debug("Requesting database connection from the pool");
        return dataSource.getConnection();
    }

    public Configuration getConfig() {
        return config;
    }

    public int getLookupCount() {
        return lookupCount.intValue();
    }

    @Override
    public void incrementLookupCount() {
        lookupCount.incrementAndGet();
    }

    public int getSuccessfulLookupCount() {
        return successfulLookupCount.intValue();
    }

    @Override
    public void incrementSuccessfulLookupCount() {
        successfulLookupCount.incrementAndGet();
    }

    public int getSubmissionCount() {
        return submissionCount.intValue();
    }

    @Override
    public void incrementSubmissionCount() {
        submissionCount.incrementAndGet();
    }

}

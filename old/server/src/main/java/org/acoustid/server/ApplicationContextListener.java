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
 
import com.google.inject.Guice;
import com.google.inject.Injector;
import javax.servlet.ServletContext;
import javax.servlet.ServletContextEvent;
import javax.servlet.ServletContextListener;
import org.apache.commons.configuration.ConfigurationException;
import org.apache.commons.configuration.XMLConfiguration;
import org.apache.log4j.Logger;
 
public class ApplicationContextListener implements ServletContextListener {

    private static final Logger logger = Logger.getLogger(ApplicationContextListener.class);

    public static final String INJECTOR_ATTRIBUTE_NAME = ApplicationContextListener.class.getName();

    @Override
    public void contextInitialized(ServletContextEvent event) {
        ServletContext servletContext = event.getServletContext();
        String configFileName = servletContext.getInitParameter("config");
        logger.info("Loading configuration from " + configFileName);
        XMLConfiguration config;
        try {
            config = new XMLConfiguration(configFileName);
        } catch (ConfigurationException ex) {
            throw new RuntimeException("Couldn't load configuration file", ex);
        }
        Injector injector = Guice.createInjector(new ServerModule(config));
        logger.debug("Setting injector");
        servletContext.setAttribute(INJECTOR_ATTRIBUTE_NAME, injector);
    }

    @Override
    public void contextDestroyed(ServletContextEvent event) {
        ServletContext servletContext = event.getServletContext();
        Injector injector = (Injector)servletContext.getAttribute(INJECTOR_ATTRIBUTE_NAME);
        if (injector == null) {
            logger.warn("Injector not found");
            return;
        }
        servletContext.removeAttribute(INJECTOR_ATTRIBUTE_NAME);

        ApplicationContext context = injector.getInstance(ApplicationContext.class);
        logger.debug("Closing application context " + context);
        context.close();
    }

}

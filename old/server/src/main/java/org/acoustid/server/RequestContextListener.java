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
 
import com.google.inject.Injector;
import javax.servlet.ServletRequestEvent;
import javax.servlet.ServletRequestListener;
import org.apache.log4j.Logger;
 
public class RequestContextListener implements ServletRequestListener {

    private static final Logger logger = Logger.getLogger(RequestContextListener.class);

    public static final String INJECTOR_ATTRIBUTE_NAME = RequestContextListener.class.getName();

    @Override
    public void requestInitialized(ServletRequestEvent sre) {
        Injector parentInjector = (Injector)sre.getServletContext().getAttribute(ApplicationContextListener.INJECTOR_ATTRIBUTE_NAME);
        if (parentInjector == null) {
            logger.error("Server injector not found");
            return;
        }
        Injector injector = parentInjector.createChildInjector(parentInjector.getInstance(RequestModule.class));
        sre.getServletRequest().setAttribute(INJECTOR_ATTRIBUTE_NAME, injector);
    }

    @Override
    public void requestDestroyed(ServletRequestEvent sre) {
        Injector injector = (Injector)sre.getServletRequest().getAttribute(INJECTOR_ATTRIBUTE_NAME);
        if (injector == null) {
            logger.error("Injector not found");
            return;
        }
        injector.getInstance(RequestContext.class).close();
        sre.getServletRequest().removeAttribute(INJECTOR_ATTRIBUTE_NAME);
    }

}

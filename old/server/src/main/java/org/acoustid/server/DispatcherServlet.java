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
import org.acoustid.server.handler.HelloHandler;
import org.acoustid.server.handler.RequestHandler;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.acoustid.server.handler.admin.StatusHandler;
import org.acoustid.server.handler.admin.MemoryStatusHandler;
import org.acoustid.server.handler.admin.SubmissionImportHandler;
import org.acoustid.server.handler.ws.LookupHandler;
import org.acoustid.server.handler.ws.SubmitHandler;
import org.acoustid.server.handler.website.IndexHandler;
import org.apache.log4j.Logger;

public class DispatcherServlet extends HttpServlet {

    private static final Logger logger = Logger.getLogger(DispatcherServlet.class);
    private Map<String, Class<? extends RequestHandler>> handlers = new HashMap<String, Class<? extends RequestHandler>>();

    public DispatcherServlet() {
        handlers.put("/hello", HelloHandler.class);
        handlers.put("/index", IndexHandler.class);
        handlers.put("/ws/lookup", LookupHandler.class);
        handlers.put("/ws/submit", SubmitHandler.class);
        handlers.put("/admin/status", StatusHandler.class);
        handlers.put("/admin/memory-status", MemoryStatusHandler.class);
        handlers.put("/admin/import", SubmissionImportHandler.class);
    }

    public Injector getInjector(HttpServletRequest request) {
        return (Injector)request.getAttribute(RequestContextListener.INJECTOR_ATTRIBUTE_NAME);
    }

    @Override
    protected void service(HttpServletRequest request, HttpServletResponse response) throws ServletException, IOException {
        Class<? extends RequestHandler> handlerClass = handlers.get(request.getRequestURI());
        if (handlerClass == null) {
            logger.warn("Handler for path " + request.getRequestURI() + " not found");
            response.setStatus(HttpServletResponse.SC_NOT_FOUND);
            return;
        }
        RequestHandler handler = getInjector(request).getInstance(handlerClass);
        try {
            handler.handle(request, response);
        }
        catch (Exception ex) {
            throw new ServletException("Internal server error", ex);
        }
    }

}

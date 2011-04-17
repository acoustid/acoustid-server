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

package org.acoustid.server.handler.admin;

import com.google.inject.Inject;
import java.io.PrintWriter;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.acoustid.SubmissionImporter;
import org.acoustid.server.handler.RequestHandler;

public class SubmissionImportHandler implements RequestHandler {

    private static final int BATCH_SIZE = 50;
    private SubmissionImporter importer;

    @Inject
    public SubmissionImportHandler(SubmissionImporter importer) {
        this.importer = importer;
    }

    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response) throws Exception {
        String batchSizeString = request.getParameter("batchSize");
        int batchSize = BATCH_SIZE;
        if (batchSizeString != null) {
            batchSize = Integer.parseInt(batchSizeString);
        }
        importer.importSubmissions(batchSize);
        PrintWriter writer = response.getWriter();
        writer.println("OK");
        response.setContentType("text/plain");
        response.setCharacterEncoding("UTF-8");
        response.setStatus(HttpServletResponse.SC_OK);
    }

}

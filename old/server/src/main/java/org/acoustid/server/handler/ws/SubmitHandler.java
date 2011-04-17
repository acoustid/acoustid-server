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

package org.acoustid.server.handler.ws;

import com.google.inject.Inject;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

import org.acoustid.Format;
import org.acoustid.Source;
import org.acoustid.SourceValidator;
import org.acoustid.Submission;
import org.acoustid.data.FormatData;
import org.acoustid.data.SubmissionData;
import org.acoustid.data.Transaction;
import org.acoustid.server.Context;
import org.acoustid.server.handler.BadRequestException;
import org.acoustid.server.util.MissingParameterException;
import org.acoustid.server.util.ParameterFormatException;
import org.acoustid.server.util.ParameterMap;
import org.acoustid.server.util.SimpleXMLStreamWriter;
import org.acoustid.util.IncompatibleFingerprintVersion;

public class SubmitHandler extends WebServiceRequestHandler {

    private static final Logger logger = Logger.getLogger(SubmitHandler.class.getName());
    private SourceValidator sourceValidator;
    private FormatData formatData;
    private SubmissionData submissionData;
    private Transaction transaction;
    private Context context;

    private class SubmissionParameters {
        public String suffix;
        public int length;
        public int bitrate;
        public String format;
        public int[] fingerprint;
        public String[] mbids;
        public String puid;
    }

    private SubmissionParameters readSubmissionParameters(ParameterMap params, String suffix) throws MissingParameterException, ParameterFormatException, IncompatibleFingerprintVersion {
        SubmissionParameters p = new SubmissionParameters();
        p.suffix = suffix;
        p.puid = params.contains("puid" + suffix)
                ? params.getUUIDString("puid" + suffix)
                : null;
        p.mbids = params.contains("mbid" + suffix)
                ? params.getUUIDStringArray("mbid" + suffix)
                : new String[] { null };
        p.length = params.getShort("length" + suffix, 1);
        p.fingerprint = params.getFingerprint("fingerprint" + suffix);
        p.bitrate = params.contains("bitrate" + suffix)
                ? params.getShort("bitrate" + suffix, 0)
                : 0;
        p.format = params.contains("format" + suffix)
                ? params.getString("format" + suffix)
                : null;
        return p;
    }

    @Override
    public void handleWebServiceRequest(SimpleXMLStreamWriter writer, ParameterMap params) throws Exception {
        List<SubmissionParameters> submissionParams = new LinkedList<SubmissionParameters>();
        if (params.contains("fingerprint.0")) {
            for (int i = 0; params.contains("fingerprint." + i); i++) {
                submissionParams.add(readSubmissionParameters(params, "." + i));
            }
        }
        else {
            submissionParams.add(readSubmissionParameters(params, ""));
        }

        /*for (SubmissionParameters p: submissionParams) {
            if (p.length <= 0) {
                throw new BadRequestException(String.format(
                        "Invalid length in parameter 'length%s' -- must be "
                        + "greater than zero.", p.suffix));
            }
            if (p.fingerprint.length <= 0) {
                throw new BadRequestException(String.format(
                        "Invalid fingerprint in parameter 'fingerprint%s'.", p.suffix));
            }
            if (!Chromaprint.isGoodFingerprintSize(p.length, p.fingerprint.length)) {
                String message =
                        "The fingerprint is too short/long for "
                        + "the specified audio length. Either the fingerprint or "
                        + "the length information is incorrect.";
                throw new HandlerException(message);
            }
        }*/

        Source source = sourceValidator.validate(params.getString("user"), params.getString("client"));

        Map<String, Format> formatCache = new HashMap<String, Format>();

        for (SubmissionParameters p: submissionParams) {
            if (p.length <= 0 || p.fingerprint.length <= 0) {
                continue;
            }
            Format format = null;
            if (p.format != null && !p.format.isEmpty()) {
                format = formatCache.get(p.format);
                if (format == null) {
                    format = formatData.findOrInsert(p.format);
                    formatCache.put(p.format, format);
                }
            }
            for (String mbid: p.mbids) {
                Submission submission = new Submission();
                submission.setData(p.fingerprint);
                submission.setLength(p.length);
                submission.setMBID(mbid);
                submission.setPUID(p.puid);
                submission.setBitrate(p.bitrate);
                submission.setSourceId(source.getId());
                if (format != null) {
                    submission.setFormatId(format.getId());
                }
                submissionData.insert(submission);
                context.incrementSubmissionCount();
            }
        }

        writer.writeStartDocument("UTF-8", "1.0");
        writer.writeStartElement("response");
        writer.writeAttribute("status", "ok");
        writer.writeEndElement();
        writer.writeEndDocument();

        transaction.commit();
        logger.log(Level.FINER, String.format("Submitted %d fingerprints", submissionParams.size()));
    }

    @Inject
    public void setSourceValidator(SourceValidator sourceValidator) {
        this.sourceValidator = sourceValidator;
    }

    @Inject
    public void setFormatData(FormatData formatData) {
        this.formatData = formatData;
    }

    @Inject
    public void setSubmissionData(SubmissionData submissionData) {
        this.submissionData = submissionData;
    }

    @Inject
    public void setTransaction(Transaction transaction) {
        this.transaction = transaction;
    }

    @Inject
    public void setContext(Context context) {
        this.context = context;
    }

}

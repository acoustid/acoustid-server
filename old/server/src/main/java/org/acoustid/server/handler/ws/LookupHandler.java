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
import java.sql.Connection;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.acoustid.Application;
import org.acoustid.FingerprintSearchResult;
import org.acoustid.Track;
import org.acoustid.data.ApplicationData;
import org.acoustid.data.FingerprintData;
import org.acoustid.data.TrackData;
import org.acoustid.server.Context;
import org.acoustid.server.handler.BadRequestException;
import org.acoustid.server.util.ParameterMap;
import org.acoustid.server.util.SimpleXMLStreamWriter;

public class LookupHandler extends WebServiceRequestHandler {

    private double IDEAL_SCORE = 0.7; // tracks above this threshold are always merged

    private Context context;
    private ApplicationData applicationData;
    private FingerprintData fingerprintData;
    private TrackData trackData;

    private class TrackResult {
        public Track track;
        public double score;
    }

    @Override
    public void handleWebServiceRequest(SimpleXMLStreamWriter writer, ParameterMap params) throws Exception {
        int includeMetadata = params.contains("meta") ? params.getInt("meta") : 0;
        String clientApiKey = params.getString("client");
        int length = params.getInt("length");
        int[] fingerprint = params.getFingerprint("fingerprint");
        double minScore = params.contains("minscore") ? params.getDouble("minscore") : 0.3;

        if (length <= 0) {
            throw new BadRequestException("Invalid length -- must be greater than zero.");
        }

        if (fingerprint.length <= 120) {
            throw new BadRequestException("Invalid fingerprint -- must be at least 120 subfingerprints.");
        }

        Application application = applicationData.findByApiKey(clientApiKey);
        if (application == null) {
            throw new BadRequestException("Application with the API key '" + clientApiKey + "' was not found.");
        }
        
        context.incrementLookupCount();

        List<FingerprintSearchResult> results = fingerprintData.search(length, fingerprint, 0, minScore, IDEAL_SCORE);

        Set<Integer> seenTracks = new HashSet<Integer>();
        List<TrackResult> trackResults = new ArrayList<TrackResult>();
        List<Track> trackList = new ArrayList<Track>();
        for (FingerprintSearchResult result : results) {
            if (!seenTracks.contains(result.getTrackId())) {
                TrackResult trackResult = new TrackResult();
                trackResult.track = new Track(result.getTrackId());
                trackResult.score = result.getScore();
                trackResults.add(trackResult);
                trackList.add(trackResult.track);
                seenTracks.add(result.getTrackId());
            }
        }

        if (includeMetadata > 0) {
            trackData.loadMBIDs(trackList);
        }

        writer.writeStartDocument("UTF-8", "1.0");
        writer.writeStartElement("response");
        writer.writeAttribute("status", "ok");
        writer.writeStartElement("results");
        for (TrackResult result : trackResults) {
            writer.writeStartElement("result");
            writer.writeTextElement("id", Integer.toString(result.track.getId()));
            writer.writeTextElement("score", Double.toString(result.score));
            if (includeMetadata > 0 && result.track.getMBIDs() != null && !result.track.getMBIDs().isEmpty()) {
                writer.writeStartElement("tracks");
                for (String mbid : result.track.getMBIDs()) {
                    writer.writeStartElement("track");
                    writer.writeTextElement("id", mbid);
                    writer.writeEndElement();
                }
                writer.writeEndElement();
            }
            writer.writeEndElement();
        }
        writer.writeEndElement();
        writer.writeEndElement();
        writer.writeEndDocument();

        if (results.size() > 0) {
        	context.incrementSuccessfulLookupCount();
        }
    }

    @Inject
    public void setContext(Context context) {
        this.context = context;
    }

    @Inject
    public void setApplicationData(ApplicationData applicationData) {
        this.applicationData = applicationData;
    }

    @Inject
    public void setFingerprintData(FingerprintData fingerprintData) {
        this.fingerprintData = fingerprintData;
    }

    @Inject
    public void setTrackData(TrackData trackData) {
        this.trackData = trackData;
    }

}

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

package org.acoustid;

public class FingerprintSearchResult {

    private double score = 0.0;
    private int fingerprintId = 0;
    private int trackId = 0;

    public FingerprintSearchResult(double score, int fingerprintId, int trackId) {
        this.score = score;
        this.fingerprintId = fingerprintId;
        this.trackId = trackId;
    }

    public FingerprintSearchResult() {
    }

    public double getScore() {
        return score;
    }

    public void setScore(double score) {
        this.score = score;
    }

    public int getFingerprintId() {
        return fingerprintId;
    }

    public void setFingerprintId(int fingerprintId) {
        this.fingerprintId = fingerprintId;
    }

    public int getTrackId() {
        return trackId;
    }

    public void setTrackId(int trackId) {
        this.trackId = trackId;
    }

}

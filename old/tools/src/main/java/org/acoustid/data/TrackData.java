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

package org.acoustid.data;

import java.sql.SQLException;
import java.util.List;
import org.acoustid.Track;

public interface TrackData {

    /**
     * Insert a new track into the database
     *
     * This method also sets the "id" attribute of the track object.
     *
     * @param track track object to be inserted
     * @return ID of the inserted track
     * @throws SQLException
     */
    int insert(Track track) throws SQLException;

    /**
     * Link the specified track to a new MBID
     *
     * @param trackId ID of the track
     * @param mbid MusicBrainz track ID (UUID)
     * @return true if it was added, false if the MBID was already linked to
     * the track before
     * @throws SQLException
     */
    boolean insertMBID(int trackId, String mbid) throws SQLException;

    void loadMBIDs(List<Track> tracks) throws SQLException;

}

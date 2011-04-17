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

import com.google.inject.AbstractModule;
import com.google.inject.Inject;
import com.google.inject.Provides;
import java.sql.Connection;
import java.sql.SQLException;
import org.acoustid.data.AccountData;
import org.acoustid.data.ApplicationData;
import org.acoustid.data.FingerprintData;
import org.acoustid.data.FormatData;
import org.acoustid.data.SourceData;
import org.acoustid.data.SubmissionData;
import org.acoustid.data.TrackData;
import org.acoustid.data.Transaction;
import org.acoustid.data.sql.SQLAccountData;
import org.acoustid.data.sql.SQLApplicationData;
import org.acoustid.data.sql.SQLFingerprintData;
import org.acoustid.data.sql.SQLFormatData;
import org.acoustid.data.sql.SQLSourceData;
import org.acoustid.data.sql.SQLSubmissionData;
import org.acoustid.data.sql.SQLTrackData;
import org.acoustid.data.sql.SQLTransaction;
import org.acoustid.musicbrainz.data.MusicBrainzPUIDData;
import org.acoustid.musicbrainz.data.sql.SQLMusicBrainzPUIDData;

public class RequestModule extends AbstractModule {

    private RequestContext context;

    @Inject
    public RequestModule(RequestContext context) {
        this.context = context;
    }

    @Provides
    protected Connection provideConnection() throws SQLException {
        return context.getConnection();
    }

    @Override
    protected void configure() {
        bind(Context.class).toInstance(context);
        bind(RequestContext.class).toInstance(context);
        bind(AccountData.class).to(SQLAccountData.class);
        bind(ApplicationData.class).to(SQLApplicationData.class);
        bind(FingerprintData.class).to(SQLFingerprintData.class);
        bind(FormatData.class).to(SQLFormatData.class);
        bind(SourceData.class).to(SQLSourceData.class);
        bind(SubmissionData.class).to(SQLSubmissionData.class);
        bind(TrackData.class).to(SQLTrackData.class);
        bind(Transaction.class).to(SQLTransaction.class);
        bind(MusicBrainzPUIDData.class).to(SQLMusicBrainzPUIDData.class);
    }

}

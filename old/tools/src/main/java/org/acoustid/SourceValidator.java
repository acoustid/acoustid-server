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

import com.google.inject.Inject;
import java.sql.SQLException;
import org.acoustid.data.AccountData;
import org.acoustid.data.ApplicationData;
import org.acoustid.data.SourceData;

public class SourceValidator {

    private ApplicationData applicationData;
    private AccountData accountData;
    private SourceData sourceData;

    @Inject
    public SourceValidator(ApplicationData applicationData, AccountData accountData, SourceData sourceData) {
        this.applicationData = applicationData;
        this.accountData = accountData;
        this.sourceData = sourceData;
    }

    public Source validate(String userApiKey, String clientApiKey) throws SQLException {
        Application application = applicationData.findByApiKey(clientApiKey);
        if (application == null) {
            throw new IllegalArgumentException("Application with the API key '" + clientApiKey + "' was not found.");
        }
        Account account = accountData.findByApiKey(userApiKey);
        if (account == null) {
            throw new IllegalArgumentException("User with the API key '" + userApiKey + "' was not found.");
        }
        return sourceData.findOrInsert(application.getId(), account.getId());
    }

}

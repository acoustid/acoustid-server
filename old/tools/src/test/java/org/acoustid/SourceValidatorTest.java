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

import java.sql.SQLException;
import org.junit.Test;
import static org.junit.Assert.*;
import static org.mockito.Mockito.*;
import java.io.IOException;
import org.acoustid.data.AccountData;
import org.acoustid.data.ApplicationData;
import org.acoustid.data.SourceData;
import org.junit.Before;

public class SourceValidatorTest {

    private AccountData accountData;
    private ApplicationData applicationData;
    private SourceData sourceData;
    private SourceValidator validator;

    @Before
    public void setUp() throws SQLException {
        accountData = mock(AccountData.class);
        applicationData = mock(ApplicationData.class);
        sourceData = mock(SourceData.class);
        validator = new SourceValidator(applicationData, accountData, sourceData);
    }

    @Test(expected=IllegalArgumentException.class)
    public void testEmptyKeys() throws IOException, SQLException {
        validator.validate("", "");
    }

    @Test(expected=IllegalArgumentException.class)
    public void testEmptyUserKey() throws IOException, SQLException {
        validator.validate("", "app");
    }

    @Test(expected=IllegalArgumentException.class)
    public void testEmptyClientKey() throws IOException, SQLException {
        validator.validate("user", "");
    }

    @Test(expected=IllegalArgumentException.class)
    public void testWrongUserKey() throws IOException, SQLException {
        when(accountData.findByApiKey("user")).thenReturn(null);
        Application app = new Application();
        app.setId(1);
        when(applicationData.findByApiKey("app")).thenReturn(app);
        validator.validate("user", "app");
    }

    @Test(expected=IllegalArgumentException.class)
    public void testWrongClientKey() throws IOException, SQLException {
        Account account = new Account();
        account.setId(2);
        when(accountData.findByApiKey("user")).thenReturn(account);
        when(applicationData.findByApiKey("app")).thenReturn(null);
        validator.validate("user", "app");
    }

    @Test
    public void testOk() throws IOException, SQLException {
        Account account = new Account();
        account.setId(2);
        when(accountData.findByApiKey("user")).thenReturn(account);
        Application app = new Application();
        app.setId(1);
        when(applicationData.findByApiKey("app")).thenReturn(app);
        Source source = new Source();
        source.setId(3);
        when(sourceData.findOrInsert(1, 2)).thenReturn(source);
        Source result = validator.validate("user", "app");
        assertEquals(source.getId(), result.getId());
    }

}

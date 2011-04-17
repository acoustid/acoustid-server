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

import org.acoustid.data.sql.DataUtils;
import org.acoustid.data.sql.SQLFingerprintData;
import org.acoustid.test.DatabaseTestCase;
import org.junit.Test;
import static org.junit.Assert.*;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import org.acoustid.Fingerprint;
import org.acoustid.FingerprintSearchResult;

public class FingerprintDataTest extends DatabaseTestCase {

    @Test
    public void testInsert() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO account (name, apikey) VALUES ('accname', 'acckey')");
        runSql(connection, "INSERT INTO application (name, version, apikey, account_id) VALUES ('appname', '1.0', 'appkey', 1)");
        runSql(connection, "INSERT INTO source (application_id, account_id) VALUES (1, 1)");
        runSql(connection, "INSERT INTO format (name) VALUES ('FLAC')");
        runSql(connection, "INSERT INTO format (name) VALUES ('MP4')");
        runSql(connection, "INSERT INTO format (name) VALUES ('WMA')");
        runSql(connection, "INSERT INTO track (id) VALUES (nextval('track_id_seq'))");
        runSql(connection, "INSERT INTO track (id) VALUES (nextval('track_id_seq'))");
        connection.commit();
        SQLFingerprintData fingerprintData = new SQLFingerprintData();
        fingerprintData.setConnection(connection);
        Fingerprint fingerprint = new Fingerprint();
        fingerprint.setLength(123);
        fingerprint.setSourceId(1);
        fingerprint.setTrackId(2);
        fingerprint.setFormatId(3);
        fingerprint.setData(new int[]{1, 2, 3});
        fingerprintData.insert(fingerprint);
        connection.commit();
        assertEquals(1, fingerprint.getId());
        Statement statement = connection.createStatement();
        ResultSet rs = statement.executeQuery("SELECT length, fingerprint, source_id, format_id, track_id FROM fingerprint WHERE id=1");
        assertTrue(rs.next());
        assertEquals(123, rs.getInt("length"));
        assertEquals("{1,2,3}", rs.getString("fingerprint"));
        assertEquals(1, rs.getInt("source_id"));
        assertEquals(2, rs.getInt("track_id"));
        assertEquals(3, rs.getInt("format_id"));
    }

    @Test
    public void testSearch() throws SQLException, ClassNotFoundException {
        int[] fingerprint = new int[] {1260302791, 1226765698, 1216267650, 1224658306, 1224592802, 1509746150, 1239180775, 1230792167, 1230447941, 1230378245, 1238768901, 1238762769, 1272186144, 1272211232, 1263854369, 1263854371, 1260302659, 1230943682, 1241433474, 1241435522, 1241370034, 1241314786, 1230792166, 1230267750, 1230447879, 1230403335, 1238783745, 1272334097, 1272202528, 1254417696, 1246028129, 1258611173, 1260303815, 1226765698, 1233044866, 1241435522, 1241374114, 1241310694, 1239180775, 1230775783, 1230386501, 1230378245, 1238768901, 1238828337, 1272186144, 1263822113, 1263854373, 1264378743, 1264498115, 1233049026, 1241433474, 1240452482, 1241357746, -914571806, -648761882, -648761882, -648632378, -640239674, -53045433, -36208297, -36404891, -44785300, -48963220, -48990740, -48857108, -48866580, -44676379, -7008283, -7071785, -2857017, -11214386, -15276594, -15272506, -44645033, -36191113, -40520665, -7031771, -2842587, -11214531, -14883555, -48302243, -48302491, -44153115, -35830043, -2865435, -3910689, -12295729, -49912370, -44663602, -61453090, -53064482, -57287298, -57346241, -53157313, -53157345, -44763633, -44698049, -11075793, -2687699, -19407769, -19606441, -28978993, -16256562, -16354354, -48867362, -48886018, -61534218, -53182482, -40601618, -40568849, -40572963, -40572980, -36378676, -11143308, -15214748, -31992028, -1105766811, -32020905, -15243450, -11078394, -36252394, -57228202, -57163690, -57282473, -40570755, -44769171, -48995220, -48923140, -48858132, -44672276, -2748699, -7073803, -2861113, -2858554, -11017778, -15272506, -11086522, -44645289, -36203465, -40520665, -2837467, -11214803, -15408867, -14813859, -48302211, -44108059, -304199963, -275495195, -271301657, -3906609, -12229170, -49908530, -44671794, -61453090, -52966018, -57281154, -57350337, -53157345, -44768753, -44763617, -11010257, -11076307, -19407763, -19540873, -29043513, -12193329, -16322098, -48859186, -48887842, -61468674, -61521946, -57380882, -40568850, -40568835, -40574004, -36378676, -44763172, -15214748, -15247516, -32025756, -32034187, -32038073, -15260338, -11127458, -36287394, -57258914, -57156513, -57281505, -57367521, -590044901, -585845477, -48914629, -15294673, -11100882, -19473042, -19606145, -29044273, -33197618, -16354866, -48876578, -65665026, -61403154, -53133330, -57376786, -1131087889, -1131092003, -1114314804, -1110120500, -1084967092, -1625827460, -1625827484, -1105865116, -1088948635, -1088952361, -1122570425, -1118372522, -1135162282, -1126710058, -1126829994, -36380553, -36380547, -44801667, -48941572, -48873492, -44680468, -2749467, -2813979, -19655225, -19634745, -11149105, -11082553, -11078201, -44640953, -44593833, -36326091, -36391643, -36391635, -44768963, -15407779, -15206531, -15276443, -11118875, -2799899, -2881561, -2878514, -44816946, -48880178, -44679730, -44675746, -40415874, -40512146, -40568962, -40574178, -36379893, -44763365, -48914641, -44654801, -11092625, -2622097, -11217569, -27995697, -32017969, -15306290, -15329794, -48886289, -44753425, -1110098449, -1131118609, -1131096083, -1114314804, -1114316084, -1110134196, -1118456292, -1088973276, -1088956892, -1122642395, -1122503145, -1122504954, -1122566858, -1126769610, -1130970026, -1114192826, -1114116026, -1076563881, -15437697, -15436547, -15385107, -15320083, -27911443, -23720211, -23851011, -19630129, -19635249, -15212081, -48826929, -65612465, -61420521, -53109705, -57297881, -53169107, -44768195, -48437987, -14813859, -14780435, -10594587, -18987291, -23312667, -19642369, -20682801, -12098098, -48862002, -65643314, -61453218, -52998818, -57281154, -57347282, -57351618, -36380129, -44763617, -44638401, -44638867, -2630555, -11217803, -11218731, -15371825, -15310386, -15321138, -48886058, -44626186, -36356122, -40603802, -40602266, -1114312355, -1114316468, -1114266684, -1109937212, -1118332940, -1122658716, -1122705692, -15409436, -15208747, -15274043, -48824873, -44645162, -36256554, -36188074, -36310954, -44765097, -44801961, -48994985, -48792219, -61441179, -36287769, -40546585, -7055673, -2857274, -27925561, -32054841, -15272713, -11086601, -2634635, -6947723, -6949788, -2821003, -44767915, -48962219, -48761003, -48830873, -36243865, -6863257, -7059865, -2861242, -11246266, -15309754, -48860090, -61471530, -53082922, -53010953, -594198553, -594268569, -590076299, -590059947, -589858987, -573090475, -573094571, -548022923, -548088459, -569051657, -568859193, -568924730, 1599526338, 1565967826, 1557513702, -590027290, -590027417, -590027417, -573250203, -539630251, -539495084, -564798092, -564798092, -564789932, -564660908, -564799532, -547884075, -581504057, -581512250, -598292778, -598222874, -598378650, -581666970, -581667482, -581687946, -573217673, 1574401143, 1574393173, 1574395221, 1607826773, 1599405429, 1599403511, 1599600087, 1599533511, 1565966790, 1549189590, 1557518310, 1557423590, 1557427687, 1557423591, 1574233461, 1607988565, 1599526212, 1599489348, 1599557905, 1582690609, -564858587, -564858521, -564681385, -547963578, -539587258, -573141178, -577396873, -40589457, -53168273, -44784849, -48979155, -15403731, -15280851, -283714179, -279519899, -279456411, -279587371, -283840057, -283646514, -283711538, -317304842, -313110554, -302690842, -306940570, -306940562, -306945665, -309042852, -36347012, -36210836, -44607628, -11184268, -11182492, -11141387, -11145531, -11014201, -11092537, -44659257, -44661561, -44576682, -44699530, -44765073, -313233297, -317430419, -317375123};
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO account (name, apikey) VALUES ('accname', 'acckey')");
        runSql(connection, "INSERT INTO application (name, version, apikey, account_id) VALUES ('appname', '1.0', 'appkey', 1)");
        runSql(connection, "INSERT INTO source (application_id, account_id) VALUES (1, 1)");
        runSql(connection, "INSERT INTO format (name) VALUES ('FLAC')");
        runSql(connection, "INSERT INTO track (id) VALUES (nextval('track_id_seq'))");
        runSql(connection, "INSERT INTO fingerprint (length, source_id, track_id, fingerprint) VALUES (80, 1, 1, '" + DataUtils.encodeIntArray(fingerprint) + "'::int[])");
        connection.commit();
        SQLFingerprintData fingerprintData = new SQLFingerprintData();
        fingerprintData.setConnection(connection);

        // Identical
        List<FingerprintSearchResult> results = fingerprintData.search(80, fingerprint);
        assertEquals(1, results.size());
        FingerprintSearchResult result = results.get(0);
        assertEquals(1.0, result.getScore(), 0.001);
        assertEquals(1, result.getFingerprintId());
        assertEquals(1, result.getTrackId());

        // Same fp, similar length
        results = fingerprintData.search(87, fingerprint);
        assertEquals(1, results.size());
        result = results.get(0);
        assertEquals(1.0, result.getScore(), 0.001);
        assertEquals(1, result.getFingerprintId());
        assertEquals(1, result.getTrackId());

        // Same fp, similar length
        results = fingerprintData.search(73, fingerprint);
        assertEquals(1, results.size());
        result = results.get(0);
        assertEquals(1.0, result.getScore(), 0.001);
        assertEquals(1, result.getFingerprintId());
        assertEquals(1, result.getTrackId());

        // Same fp, different length
        results = fingerprintData.search(88, fingerprint);
        assertEquals(0, results.size());

        // Same fp, different length
        results = fingerprintData.search(72, fingerprint);
        assertEquals(0, results.size());

        // Similar fp, same length
        int[] modifiedFingerprint = new int[fingerprint.length];
        for (int i = 0; i < fingerprint.length; i++) {
            modifiedFingerprint[i] = fingerprint[i];
            if (i % 2 == 0) {
                modifiedFingerprint[i] ^= 1;
            }
        }
        for (int i = 0; i < 10; i++) {
            modifiedFingerprint[i] = 0;
        }
        results = fingerprintData.search(80, modifiedFingerprint);
        assertEquals(1, results.size());
        result = results.get(0);
        assertEquals(0.979, result.getScore(), 0.001);
        assertEquals(1, result.getFingerprintId());
        assertEquals(1, result.getTrackId());

        // Different fp, same length
        int[] differentFingerprint = new int[fingerprint.length];
        for (int i = 0; i < fingerprint.length; i++) {
            differentFingerprint[i] = fingerprint[i] ^ 3;
        }
        results = fingerprintData.search(80, differentFingerprint);
        assertEquals(0, results.size());

        // Optimistic (partial) search
        results = fingerprintData.search(80, modifiedFingerprint, 0, 0.1, 0.7);
        assertEquals(1, results.size());
        result = results.get(0);
        assertEquals(0.979, result.getScore(), 0.001);
        assertEquals(1, result.getFingerprintId());
        assertEquals(1, result.getTrackId());

        // Optimistic (partial) search with too high threshold -- returns duplicates
        results = fingerprintData.search(80, modifiedFingerprint, 0, 0.1, 0.99);
        assertEquals(2, results.size());
        result = results.get(0);
        assertEquals(0.979, result.getScore(), 0.001);
        assertEquals(1, result.getFingerprintId());
        assertEquals(1, result.getTrackId());
        result = results.get(1);
        assertEquals(0.979, result.getScore(), 0.001);
        assertEquals(1, result.getFingerprintId());
        assertEquals(1, result.getTrackId());
    }

    @Test
    public void testSearchShortTrack() throws SQLException, ClassNotFoundException {
        int[] fingerprint = new int[] {1260302791, 1226765698, 1216267650, 1224658306, 1224592802, 1509746150, 1239180775, 1230792167, 1230447941, 1230378245, 1238768901, 1238762769, 1272186144, 1272211232, 1263854369, 1263854371, 1260302659, 1230943682, 1241433474, 1241435522, 1241370034, 1241314786, 1230792166, 1230267750, 1230447879, 1230403335, 1238783745, 1272334097, 1272202528, 1254417696, 1246028129, 1258611173, 1260303815, 1226765698, 1233044866, 1241435522, 1241374114, 1241310694, 1239180775, 1230775783, 1230386501, 1230378245, 1238768901, 1238828337, 1272186144, 1263822113, 1263854373, 1264378743, 1264498115, 1233049026, 1241433474, 1240452482, 1241357746, -914571806, -648761882, -648761882, -648632378, -640239674, -53045433, -36208297, -36404891, -44785300, -48963220, -48990740, -48857108, -48866580, -44676379, -7008283, -7071785, -2857017, -11214386, -15276594, -15272506, -44645033, -36191113, -40520665, -7031771, -2842587, -11214531, -14883555, -48302243, -48302491, -44153115, -35830043, -2865435, -3910689, -12295729, -49912370, -44663602, -61453090, -53064482, -57287298, -57346241, -53157313, -53157345, -44763633, -44698049, -11075793, -2687699, -19407769, -19606441, -28978993, -16256562, -16354354, -48867362, -48886018, -61534218, -53182482, -40601618, -40568849, -40572963, -40572980, -36378676, -11143308, -15214748, -31992028, -1105766811, -32020905, -15243450, -11078394, -36252394, -57228202, -57163690, -57282473, -40570755, -44769171, -48995220, -48923140, -48858132, -44672276, -2748699, -7073803, -2861113, -2858554, -11017778, -15272506, -11086522, -44645289, -36203465, -40520665, -2837467, -11214803, -15408867, -14813859, -48302211, -44108059, -304199963, -275495195, -271301657};
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO account (name, apikey) VALUES ('accname', 'acckey')");
        runSql(connection, "INSERT INTO application (name, version, apikey, account_id) VALUES ('appname', '1.0', 'appkey', 1)");
        runSql(connection, "INSERT INTO source (application_id, account_id) VALUES (1, 1)");
        runSql(connection, "INSERT INTO format (name) VALUES ('FLAC')");
        runSql(connection, "INSERT INTO track (id) VALUES (nextval('track_id_seq'))");
        runSql(connection, "INSERT INTO fingerprint (length, source_id, track_id, fingerprint) VALUES (20, 1, 1, '" + DataUtils.encodeIntArray(fingerprint) + "'::int[])");
        connection.commit();
        SQLFingerprintData fingerprintData = new SQLFingerprintData();
        fingerprintData.setConnection(connection);

        // Identical
        List<FingerprintSearchResult> results = fingerprintData.search(20, fingerprint);
        assertEquals(1, results.size());
        FingerprintSearchResult result = results.get(0);
        assertEquals(1.0, result.getScore(), 0.001);
        assertEquals(1, result.getFingerprintId());
        assertEquals(1, result.getTrackId());

        // Same fp, similar length
        results = fingerprintData.search(27, fingerprint);
        assertEquals(1, results.size());
        result = results.get(0);
        assertEquals(1.0, result.getScore(), 0.001);
        assertEquals(1, result.getFingerprintId());
        assertEquals(1, result.getTrackId());

        // Same fp, similar length
        results = fingerprintData.search(13, fingerprint);
        assertEquals(1, results.size());
        result = results.get(0);
        assertEquals(1.0, result.getScore(), 0.001);
        assertEquals(1, result.getFingerprintId());
        assertEquals(1, result.getTrackId());

        // Same fp, different length
        results = fingerprintData.search(28, fingerprint);
        assertEquals(0, results.size());

        // Same fp, different length
        results = fingerprintData.search(12, fingerprint);
        assertEquals(0, results.size());

        // Similar fp, same length
        int[] modifiedFingerprint = new int[fingerprint.length];
        for (int i = 0; i < fingerprint.length; i++) {
            modifiedFingerprint[i] = fingerprint[i];
            if (i % 2 == 0) {
                modifiedFingerprint[i] ^= 1;
            }
        }
        for (int i = 0; i < 10; i++) {
            modifiedFingerprint[i] = 0;
        }
        results = fingerprintData.search(20, modifiedFingerprint);
        assertEquals(1, results.size());
        result = results.get(0);
        assertEquals(0.932, result.getScore(), 0.001);
        assertEquals(1, result.getFingerprintId());
        assertEquals(1, result.getTrackId());

        // Different fp, same length
        int[] differentFingerprint = new int[fingerprint.length];
        for (int i = 0; i < fingerprint.length; i++) {
            differentFingerprint[i] = fingerprint[i] ^ 3;
        }
        results = fingerprintData.search(20, differentFingerprint);
        assertEquals(0, results.size());
    }


    @Test
    public void testSearchSilence() throws SQLException, ClassNotFoundException {
        int[] fingerprint = new int[400];
        for (int i = 0; i < 400; i++) {
            fingerprint[i] = 627964279;
        }
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO account (name, apikey) VALUES ('accname', 'acckey')");
        runSql(connection, "INSERT INTO application (name, version, apikey, account_id) VALUES ('appname', '1.0', 'appkey', 1)");
        runSql(connection, "INSERT INTO source (application_id, account_id) VALUES (1, 1)");
        runSql(connection, "INSERT INTO format (name) VALUES ('FLAC')");
        runSql(connection, "INSERT INTO track (id) VALUES (nextval('track_id_seq'))");
        runSql(connection, "INSERT INTO fingerprint (length, source_id, track_id, fingerprint) VALUES (80, 1, 1, '" + DataUtils.encodeIntArray(fingerprint) + "'::int[])");
        connection.commit();
        SQLFingerprintData fingerprintData = new SQLFingerprintData();
        fingerprintData.setConnection(connection);

        // Identical, but doesn't find anything because silence subfingerprints are not indexed
        List<FingerprintSearchResult> results = fingerprintData.search(80, fingerprint);
        assertEquals(0, results.size());
    }

    @Test
    public void testSearchMultipleAll() throws SQLException, ClassNotFoundException {
        int[] fingerprint = new int[] {1260302791, 1226765698, 1216267650, 1224658306, 1224592802, 1509746150, 1239180775, 1230792167, 1230447941, 1230378245, 1238768901, 1238762769, 1272186144, 1272211232, 1263854369, 1263854371, 1260302659, 1230943682, 1241433474, 1241435522, 1241370034, 1241314786, 1230792166, 1230267750, 1230447879, 1230403335, 1238783745, 1272334097, 1272202528, 1254417696, 1246028129, 1258611173, 1260303815, 1226765698, 1233044866, 1241435522, 1241374114, 1241310694, 1239180775, 1230775783, 1230386501, 1230378245, 1238768901, 1238828337, 1272186144, 1263822113, 1263854373, 1264378743, 1264498115, 1233049026, 1241433474, 1240452482, 1241357746, -914571806, -648761882, -648761882, -648632378, -640239674, -53045433, -36208297, -36404891, -44785300, -48963220, -48990740, -48857108, -48866580, -44676379, -7008283, -7071785, -2857017, -11214386, -15276594, -15272506, -44645033, -36191113, -40520665, -7031771, -2842587, -11214531, -14883555, -48302243, -48302491, -44153115, -35830043, -2865435, -3910689, -12295729, -49912370, -44663602, -61453090, -53064482, -57287298, -57346241, -53157313, -53157345, -44763633, -44698049, -11075793, -2687699, -19407769, -19606441, -28978993, -16256562, -16354354, -48867362, -48886018, -61534218, -53182482, -40601618, -40568849, -40572963, -40572980, -36378676, -11143308, -15214748, -31992028, -1105766811, -32020905, -15243450, -11078394, -36252394, -57228202, -57163690, -57282473, -40570755, -44769171, -48995220, -48923140, -48858132, -44672276, -2748699, -7073803, -2861113, -2858554, -11017778, -15272506, -11086522, -44645289, -36203465, -40520665, -2837467, -11214803, -15408867, -14813859, -48302211, -44108059, -304199963, -275495195, -271301657, -3906609, -12229170, -49908530, -44671794, -61453090, -52966018, -57281154, -57350337, -53157345, -44768753, -44763617, -11010257, -11076307, -19407763, -19540873, -29043513, -12193329, -16322098, -48859186, -48887842, -61468674, -61521946, -57380882, -40568850, -40568835, -40574004, -36378676, -44763172, -15214748, -15247516, -32025756, -32034187, -32038073, -15260338, -11127458, -36287394, -57258914, -57156513, -57281505, -57367521, -590044901, -585845477, -48914629, -15294673, -11100882, -19473042, -19606145, -29044273, -33197618, -16354866, -48876578, -65665026, -61403154, -53133330, -57376786, -1131087889, -1131092003, -1114314804, -1110120500, -1084967092, -1625827460, -1625827484, -1105865116, -1088948635, -1088952361, -1122570425, -1118372522, -1135162282, -1126710058, -1126829994, -36380553, -36380547, -44801667, -48941572, -48873492, -44680468, -2749467, -2813979, -19655225, -19634745, -11149105, -11082553, -11078201, -44640953, -44593833, -36326091, -36391643, -36391635, -44768963, -15407779, -15206531, -15276443, -11118875, -2799899, -2881561, -2878514, -44816946, -48880178, -44679730, -44675746, -40415874, -40512146, -40568962, -40574178, -36379893, -44763365, -48914641, -44654801, -11092625, -2622097, -11217569, -27995697, -32017969, -15306290, -15329794, -48886289, -44753425, -1110098449, -1131118609, -1131096083, -1114314804, -1114316084, -1110134196, -1118456292, -1088973276, -1088956892, -1122642395, -1122503145, -1122504954, -1122566858, -1126769610, -1130970026, -1114192826, -1114116026, -1076563881, -15437697, -15436547, -15385107, -15320083, -27911443, -23720211, -23851011, -19630129, -19635249, -15212081, -48826929, -65612465, -61420521, -53109705, -57297881, -53169107, -44768195, -48437987, -14813859, -14780435, -10594587, -18987291, -23312667, -19642369, -20682801, -12098098, -48862002, -65643314, -61453218, -52998818, -57281154, -57347282, -57351618, -36380129, -44763617, -44638401, -44638867, -2630555, -11217803, -11218731, -15371825, -15310386, -15321138, -48886058, -44626186, -36356122, -40603802, -40602266, -1114312355, -1114316468, -1114266684, -1109937212, -1118332940, -1122658716, -1122705692, -15409436, -15208747, -15274043, -48824873, -44645162, -36256554, -36188074, -36310954, -44765097, -44801961, -48994985, -48792219, -61441179, -36287769, -40546585, -7055673, -2857274, -27925561, -32054841, -15272713, -11086601, -2634635, -6947723, -6949788, -2821003, -44767915, -48962219, -48761003, -48830873, -36243865, -6863257, -7059865, -2861242, -11246266, -15309754, -48860090, -61471530, -53082922, -53010953, -594198553, -594268569, -590076299, -590059947, -589858987, -573090475, -573094571, -548022923, -548088459, -569051657, -568859193, -568924730, 1599526338, 1565967826, 1557513702, -590027290, -590027417, -590027417, -573250203, -539630251, -539495084, -564798092, -564798092, -564789932, -564660908, -564799532, -547884075, -581504057, -581512250, -598292778, -598222874, -598378650, -581666970, -581667482, -581687946, -573217673, 1574401143, 1574393173, 1574395221, 1607826773, 1599405429, 1599403511, 1599600087, 1599533511, 1565966790, 1549189590, 1557518310, 1557423590, 1557427687, 1557423591, 1574233461, 1607988565, 1599526212, 1599489348, 1599557905, 1582690609, -564858587, -564858521, -564681385, -547963578, -539587258, -573141178, -577396873, -40589457, -53168273, -44784849, -48979155, -15403731, -15280851, -283714179, -279519899, -279456411, -279587371, -283840057, -283646514, -283711538, -317304842, -313110554, -302690842, -306940570, -306940562, -306945665, -309042852, -36347012, -36210836, -44607628, -11184268, -11182492, -11141387, -11145531, -11014201, -11092537, -44659257, -44661561, -44576682, -44699530, -44765073, -313233297, -317430419, -317375123};
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO account (name, apikey) VALUES ('accname', 'acckey')");
        runSql(connection, "INSERT INTO application (name, version, apikey, account_id) VALUES ('appname', '1.0', 'appkey', 1)");
        runSql(connection, "INSERT INTO source (application_id, account_id) VALUES (1, 1)");
        runSql(connection, "INSERT INTO format (name) VALUES ('FLAC')");
        runSql(connection, "INSERT INTO track (id) VALUES (nextval('track_id_seq'))");
        runSql(connection, "INSERT INTO fingerprint (length, source_id, track_id, fingerprint) VALUES (80, 1, 1, '" + DataUtils.encodeIntArray(fingerprint) + "'::int[])");
        runSql(connection, "INSERT INTO fingerprint (length, source_id, track_id, fingerprint) VALUES (81, 1, 1, '" + DataUtils.encodeIntArray(fingerprint) + "'::int[])");
        connection.commit();
        SQLFingerprintData fingerprintData = new SQLFingerprintData();
        fingerprintData.setConnection(connection);

        List<FingerprintSearchResult> results = fingerprintData.search(80, fingerprint);
        assertEquals(2, results.size());
        FingerprintSearchResult result = results.get(0);
        assertEquals(1.0, result.getScore(), 0.001);
        assertEquals(1, result.getFingerprintId());
        assertEquals(1, result.getTrackId());
        result = results.get(1);
        assertEquals(1.0, result.getScore(), 0.001);
        assertEquals(2, result.getFingerprintId());
        assertEquals(1, result.getTrackId());
    }

    @Test
    public void testSearchMultipleFirst() throws SQLException, ClassNotFoundException {
        int[] fingerprint = new int[] {1260302791, 1226765698, 1216267650, 1224658306, 1224592802, 1509746150, 1239180775, 1230792167, 1230447941, 1230378245, 1238768901, 1238762769, 1272186144, 1272211232, 1263854369, 1263854371, 1260302659, 1230943682, 1241433474, 1241435522, 1241370034, 1241314786, 1230792166, 1230267750, 1230447879, 1230403335, 1238783745, 1272334097, 1272202528, 1254417696, 1246028129, 1258611173, 1260303815, 1226765698, 1233044866, 1241435522, 1241374114, 1241310694, 1239180775, 1230775783, 1230386501, 1230378245, 1238768901, 1238828337, 1272186144, 1263822113, 1263854373, 1264378743, 1264498115, 1233049026, 1241433474, 1240452482, 1241357746, -914571806, -648761882, -648761882, -648632378, -640239674, -53045433, -36208297, -36404891, -44785300, -48963220, -48990740, -48857108, -48866580, -44676379, -7008283, -7071785, -2857017, -11214386, -15276594, -15272506, -44645033, -36191113, -40520665, -7031771, -2842587, -11214531, -14883555, -48302243, -48302491, -44153115, -35830043, -2865435, -3910689, -12295729, -49912370, -44663602, -61453090, -53064482, -57287298, -57346241, -53157313, -53157345, -44763633, -44698049, -11075793, -2687699, -19407769, -19606441, -28978993, -16256562, -16354354, -48867362, -48886018, -61534218, -53182482, -40601618, -40568849, -40572963, -40572980, -36378676, -11143308, -15214748, -31992028, -1105766811, -32020905, -15243450, -11078394, -36252394, -57228202, -57163690, -57282473, -40570755, -44769171, -48995220, -48923140, -48858132, -44672276, -2748699, -7073803, -2861113, -2858554, -11017778, -15272506, -11086522, -44645289, -36203465, -40520665, -2837467, -11214803, -15408867, -14813859, -48302211, -44108059, -304199963, -275495195, -271301657, -3906609, -12229170, -49908530, -44671794, -61453090, -52966018, -57281154, -57350337, -53157345, -44768753, -44763617, -11010257, -11076307, -19407763, -19540873, -29043513, -12193329, -16322098, -48859186, -48887842, -61468674, -61521946, -57380882, -40568850, -40568835, -40574004, -36378676, -44763172, -15214748, -15247516, -32025756, -32034187, -32038073, -15260338, -11127458, -36287394, -57258914, -57156513, -57281505, -57367521, -590044901, -585845477, -48914629, -15294673, -11100882, -19473042, -19606145, -29044273, -33197618, -16354866, -48876578, -65665026, -61403154, -53133330, -57376786, -1131087889, -1131092003, -1114314804, -1110120500, -1084967092, -1625827460, -1625827484, -1105865116, -1088948635, -1088952361, -1122570425, -1118372522, -1135162282, -1126710058, -1126829994, -36380553, -36380547, -44801667, -48941572, -48873492, -44680468, -2749467, -2813979, -19655225, -19634745, -11149105, -11082553, -11078201, -44640953, -44593833, -36326091, -36391643, -36391635, -44768963, -15407779, -15206531, -15276443, -11118875, -2799899, -2881561, -2878514, -44816946, -48880178, -44679730, -44675746, -40415874, -40512146, -40568962, -40574178, -36379893, -44763365, -48914641, -44654801, -11092625, -2622097, -11217569, -27995697, -32017969, -15306290, -15329794, -48886289, -44753425, -1110098449, -1131118609, -1131096083, -1114314804, -1114316084, -1110134196, -1118456292, -1088973276, -1088956892, -1122642395, -1122503145, -1122504954, -1122566858, -1126769610, -1130970026, -1114192826, -1114116026, -1076563881, -15437697, -15436547, -15385107, -15320083, -27911443, -23720211, -23851011, -19630129, -19635249, -15212081, -48826929, -65612465, -61420521, -53109705, -57297881, -53169107, -44768195, -48437987, -14813859, -14780435, -10594587, -18987291, -23312667, -19642369, -20682801, -12098098, -48862002, -65643314, -61453218, -52998818, -57281154, -57347282, -57351618, -36380129, -44763617, -44638401, -44638867, -2630555, -11217803, -11218731, -15371825, -15310386, -15321138, -48886058, -44626186, -36356122, -40603802, -40602266, -1114312355, -1114316468, -1114266684, -1109937212, -1118332940, -1122658716, -1122705692, -15409436, -15208747, -15274043, -48824873, -44645162, -36256554, -36188074, -36310954, -44765097, -44801961, -48994985, -48792219, -61441179, -36287769, -40546585, -7055673, -2857274, -27925561, -32054841, -15272713, -11086601, -2634635, -6947723, -6949788, -2821003, -44767915, -48962219, -48761003, -48830873, -36243865, -6863257, -7059865, -2861242, -11246266, -15309754, -48860090, -61471530, -53082922, -53010953, -594198553, -594268569, -590076299, -590059947, -589858987, -573090475, -573094571, -548022923, -548088459, -569051657, -568859193, -568924730, 1599526338, 1565967826, 1557513702, -590027290, -590027417, -590027417, -573250203, -539630251, -539495084, -564798092, -564798092, -564789932, -564660908, -564799532, -547884075, -581504057, -581512250, -598292778, -598222874, -598378650, -581666970, -581667482, -581687946, -573217673, 1574401143, 1574393173, 1574395221, 1607826773, 1599405429, 1599403511, 1599600087, 1599533511, 1565966790, 1549189590, 1557518310, 1557423590, 1557427687, 1557423591, 1574233461, 1607988565, 1599526212, 1599489348, 1599557905, 1582690609, -564858587, -564858521, -564681385, -547963578, -539587258, -573141178, -577396873, -40589457, -53168273, -44784849, -48979155, -15403731, -15280851, -283714179, -279519899, -279456411, -279587371, -283840057, -283646514, -283711538, -317304842, -313110554, -302690842, -306940570, -306940562, -306945665, -309042852, -36347012, -36210836, -44607628, -11184268, -11182492, -11141387, -11145531, -11014201, -11092537, -44659257, -44661561, -44576682, -44699530, -44765073, -313233297, -317430419, -317375123};
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO account (name, apikey) VALUES ('accname', 'acckey')");
        runSql(connection, "INSERT INTO application (name, version, apikey, account_id) VALUES ('appname', '1.0', 'appkey', 1)");
        runSql(connection, "INSERT INTO source (application_id, account_id) VALUES (1, 1)");
        runSql(connection, "INSERT INTO format (name) VALUES ('FLAC')");
        runSql(connection, "INSERT INTO track (id) VALUES (nextval('track_id_seq'))");
        runSql(connection, "INSERT INTO fingerprint (length, source_id, track_id, fingerprint) VALUES (80, 1, 1, '" + DataUtils.encodeIntArray(fingerprint) + "'::int[])");
        runSql(connection, "INSERT INTO fingerprint (length, source_id, track_id, fingerprint) VALUES (81, 1, 1, '" + DataUtils.encodeIntArray(fingerprint) + "'::int[])");
        connection.commit();
        SQLFingerprintData fingerprintData = new SQLFingerprintData();
        fingerprintData.setConnection(connection);

        List<FingerprintSearchResult> results = fingerprintData.search(80, fingerprint, 1);
        assertEquals(1, results.size());
        FingerprintSearchResult result = results.get(0);
        assertEquals(1.0, result.getScore(), 0.001);
        assertEquals(1, result.getFingerprintId());
        assertEquals(1, result.getTrackId());
    }

}

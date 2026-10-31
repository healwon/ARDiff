public class fixedV {
    // reference fix: keep the named thresholds and g + 1, make the top test inclusive again
    public static double snippet(int score) {
        int pass = 60;
        int top = pass + 30;
        int g = 0;
        if (score >= pass) {
            g = 1;
        }
        if (score >= top) {
            g = g + 1;
        }
        return g;
    }
}

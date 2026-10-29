public class oldV {
    // readable: 0 below 60, 1 from 60, 2 from 90
    public static double snippet(int score) {
        int g = 0;
        if (score >= 60) {
            g = 1;
        }
        if (score >= 90) {
            g = 2;
        }
        return g;
    }
}

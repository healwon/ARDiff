public class oldV {
    // before: pay is counted at the rate up to 40 hours,
    //         every hour beyond at 1.5 times the rate 
    //         (x1.5 applied to the rate and then rounded down)
    public static double snippet(int hours, int rate, int holiday) {
        int pay = 0;
        if (hours <= 40) {
            pay = hours * rate;
        }
        else {
            pay = 40 * rate + (hours - 40) * (rate * 3 / 2);
        }
        return pay;
    }
}
